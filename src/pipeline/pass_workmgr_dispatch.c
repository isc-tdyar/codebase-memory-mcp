#include "pipeline/pass_workmgr_dispatch.h"
#include "pipeline/pipeline_internal.h"
#include "graph_buffer/graph_buffer.h"
#include "foundation/log.h"
#include "foundation/compat.h"
#include "foundation/compat_fs.h"
#include "foundation/constants.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <ctype.h>

/* WorkMgr dispatch: `##class(%SYSTEM.WorkMgr).Queue("##class(Pkg.Cls).Method", ...)`
 * names its target as a string literal. This pass resolves that literal to the
 * target ClassMethod node and emits a CALLS edge from the calling method, so the
 * static graph sees the work-queue hop the regular call extractor cannot. */

#define CONF_LITERAL 0.95
#define CONF_CALLBACK 0.90
#define MAX_QUEUE_TARGETS 64

/* ── Language gate ───────────────────────────────────────────────── */

typedef struct {
    bool found;
} wm_lang_check_t;

static void check_objectscript_node(const cbm_gbuf_node_t *node, void *userdata) {
    wm_lang_check_t *s = (wm_lang_check_t *)userdata;
    if (s->found || !node->file_path)
        return;
    const char *fp = node->file_path;
    size_t len = strlen(fp);
    if (len >= 4 && (strcmp(fp + len - 4, ".cls") == 0 || strcmp(fp + len - 4, ".mac") == 0 ||
                     strcmp(fp + len - 4, ".int") == 0)) {
        s->found = true;
    }
}

static bool has_objectscript_nodes(cbm_gbuf_t *gbuf) {
    wm_lang_check_t state = {false};
    cbm_gbuf_foreach_node(gbuf, check_objectscript_node, &state);
    return state.found;
}

/* ── File reader ─────────────────────────────────────────────────── */

static char *read_file(const char *full_path) {
    FILE *f = cbm_fopen(full_path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz <= 0 || sz > 8 * 1024 * 1024) {
        fclose(f);
        return NULL;
    }
    char *buf = malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    size_t got = fread(buf, 1, (size_t)sz, f);
    buf[got] = '\0';
    fclose(f);
    return buf;
}

/* ── Target model ────────────────────────────────────────────────── */

typedef struct {
    char class_qn[CBM_SZ_256];
    char method_name[CBM_SZ_256];
    char via[CBM_SZ_64]; /* Queue | QueueCallback | QueueCallback_cb | QueueChild */
    double confidence;
} wm_target_t;

/* Parse "##class(Pkg.Class).Method" → class_qn + method_name.
 * Returns false when malformed, or when the class is a %SYSTEM / %Library
 * system class: those are never in the user corpus, so no edge can resolve. */
static bool parse_class_method_literal(const char *literal, char *class_qn, int class_sz,
                                       char *method_name, int method_sz) {
    class_qn[0] = '\0';
    method_name[0] = '\0';
    if (!literal)
        return false;
    const char *start = strstr(literal, "##class(");
    if (!start)
        return false;
    start += 8; /* strlen("##class(") */
    const char *end = strchr(start, ')');
    if (!end)
        return false;
    int clen = (int)(end - start);
    if (clen <= 0 || clen >= class_sz)
        return false;
    if (start[0] == '%')
        return false;
    memcpy(class_qn, start, (size_t)clen);
    class_qn[clen] = '\0';

    const char *dot = end + 1;
    if (*dot != '.')
        return false;
    dot++;
    int mlen = 0;
    while (dot[mlen] && (isalnum((unsigned char)dot[mlen]) || dot[mlen] == '_' || dot[mlen] == '%'))
        mlen++;
    if (mlen <= 0 || mlen >= method_sz)
        return false;
    memcpy(method_name, dot, (size_t)mlen);
    method_name[mlen] = '\0';
    return true;
}

/* Copy the next double-quoted string in [p, limit) into out.
 * Returns the position just past the closing quote, or NULL. */
static const char *extract_quoted(const char *p, const char *limit, char *out, int outsz) {
    while (p < limit && *p != '"')
        p++;
    if (p >= limit)
        return NULL;
    p++;
    const char *end = p;
    while (end < limit && *end != '"')
        end++;
    if (end >= limit)
        return NULL;
    int len = (int)(end - p);
    if (len >= outsz)
        len = outsz - 1;
    memcpy(out, p, (size_t)len);
    out[len] = '\0';
    return end + 1;
}

/* Skip one comma-separated argument (paren/bracket aware). Returns the
 * position after the comma, or NULL when the argument list ends first. */
static const char *skip_first_arg(const char *p, const char *limit) {
    int depth = 0;
    while (p < limit) {
        if (*p == '(' || *p == '[')
            depth++;
        else if (*p == ')' || *p == ']') {
            if (depth == 0)
                return NULL;
            depth--;
        } else if (*p == ',' && depth == 0)
            return p + 1;
        p++;
    }
    return NULL;
}

static const char *WM_CLASSES[] = {"##class(%SYSTEM.WorkMgr)", "##class(%SYSTEM.WorkMgrThread)",
                                   NULL};
static const char *WM_METHODS[] = {"Queue", "QueueCallback", "QueueChild", NULL};

/* True when the ")." at `paren` closes one of the WorkMgr class references. */
static bool preceded_by_workmgr_class(const char *body_start, const char *paren) {
    for (int ci = 0; WM_CLASSES[ci]; ci++) {
        size_t clen = strlen(WM_CLASSES[ci]); /* includes the trailing ')' */
        const char *cand = paren - (clen - 1);
        if (cand >= body_start && memcmp(cand, WM_CLASSES[ci], clen) == 0)
            return true;
    }
    return false;
}

static void push_target(wm_target_t *targets, int *count, int max, const char *lit, const char *via,
                        double confidence) {
    if (*count >= max)
        return;
    wm_target_t t;
    memset(&t, 0, sizeof(t));
    if (!parse_class_method_literal(lit, t.class_qn, CBM_SZ_256, t.method_name, CBM_SZ_256))
        return;
    snprintf(t.via, sizeof(t.via), "%s", via);
    t.confidence = confidence;
    targets[(*count)++] = t;
}

/* Scan one brace-bounded method body for WorkMgr Queue* calls. */
static int scan_workmgr_targets(const char *body_start, const char *body_end, wm_target_t *targets,
                                int max) {
    int count = 0;
    const char *p = body_start;

    while (p < body_end && count < max) {
        const char *best = NULL;
        int best_mi = -1;
        for (int mi = 0; WM_METHODS[mi]; mi++) {
            char needle[64];
            snprintf(needle, sizeof(needle), ").%s(", WM_METHODS[mi]);
            const char *hit = strstr(p, needle);
            if (hit && hit < body_end && (!best || hit < best)) {
                best = hit;
                best_mi = mi;
            }
        }
        if (!best)
            break;

        bool is_wm = preceded_by_workmgr_class(body_start, best);
        const char *wm_name = WM_METHODS[best_mi];
        /* Advance past ").Name(" regardless, so an unrelated match cannot loop. */
        p = best + 2 + strlen(wm_name) + 1;
        if (!is_wm)
            continue;

        const char *arg_start = p;
        char lit[CBM_SZ_256];

        if (strcmp(wm_name, "Queue") == 0) {
            if (extract_quoted(arg_start, body_end, lit, sizeof(lit)))
                push_target(targets, &count, max, lit, "Queue", CONF_LITERAL);
        } else if (strcmp(wm_name, "QueueCallback") == 0) {
            const char *after = extract_quoted(arg_start, body_end, lit, sizeof(lit));
            if (!after)
                continue;
            push_target(targets, &count, max, lit, "QueueCallback", CONF_LITERAL);
            /* Second argument is the completion callback, also a ##class literal. */
            const char *cb_start = skip_first_arg(arg_start, body_end);
            char cb_lit[CBM_SZ_256];
            if (cb_start && extract_quoted(cb_start, body_end, cb_lit, sizeof(cb_lit)))
                push_target(targets, &count, max, cb_lit, "QueueCallback_cb", CONF_CALLBACK);
        } else { /* QueueChild(mgr, target, ...) — target is the second argument */
            const char *after_mgr = skip_first_arg(arg_start, body_end);
            if (after_mgr && extract_quoted(after_mgr, body_end, lit, sizeof(lit)))
                push_target(targets, &count, max, lit, "QueueChild", CONF_LITERAL);
        }
    }
    return count;
}

/* Locate the brace-delimited body of `Method name(` / `ClassMethod name(`. */
static bool find_method_body(const char *source, const char *method_name, const char **body_start,
                             const char **body_end) {
    static const char *FORMS[] = {"Method %s(", "Method %s ", "ClassMethod %s(", "ClassMethod %s ",
                                  NULL};
    const char *bs = NULL;
    for (int i = 0; FORMS[i] && !bs; i++) {
        char needle[CBM_SZ_256];
        snprintf(needle, sizeof(needle), FORMS[i], method_name);
        bs = strstr(source, needle);
    }
    if (!bs)
        return false;

    const char *brace = strchr(bs, '{');
    if (!brace)
        return false;

    int depth = 0;
    const char *be = brace;
    while (*be) {
        if (*be == '{')
            depth++;
        else if (*be == '}') {
            depth--;
            if (depth == 0)
                break;
        }
        be++;
    }

    *body_start = brace;
    *body_end = be;
    return true;
}

/* Resolve "<class_qn>.<method>" to a Method node. Stored qualified names
 * carry a project/module prefix (e.g. "<project>.Worker.MyApp.Worker.Run"),
 * so an exact hashtable lookup on the bare ObjectScript name never matches.
 * Look up by method name, then require the qualified name to equal the bare
 * form or end with ".<class_qn>.<method>" (segment-anchored). */
static const cbm_gbuf_node_t *resolve_target_method(cbm_pipeline_ctx_t *ctx, const char *class_qn,
                                                    const char *method_name) {
    char suffix[CBM_SZ_512];
    int slen = snprintf(suffix, sizeof(suffix), "%s.%s", class_qn, method_name);
    if (slen <= 0 || slen >= (int)sizeof(suffix))
        return NULL;

    const cbm_gbuf_node_t **nodes = NULL;
    int count = 0;
    cbm_gbuf_find_by_name(ctx->gbuf, method_name, (const cbm_gbuf_node_t ***)&nodes, &count);
    for (int i = 0; i < count; i++) {
        const cbm_gbuf_node_t *n = nodes[i];
        if (!n->qualified_name || !n->label || strcmp(n->label, "Method") != 0)
            continue;
        size_t qlen = strlen(n->qualified_name);
        if (qlen == (size_t)slen && strcmp(n->qualified_name, suffix) == 0)
            return n;
        if (qlen > (size_t)slen && n->qualified_name[qlen - (size_t)slen - 1] == '.' &&
            strcmp(n->qualified_name + qlen - (size_t)slen, suffix) == 0)
            return n;
    }
    return NULL;
}

/* ── Main pass ───────────────────────────────────────────────────── */

void cbm_pipeline_pass_workmgr_dispatch(cbm_pipeline_ctx_t *ctx) {
    if (!ctx || !ctx->gbuf || !ctx->repo_path)
        return;

    if (!has_objectscript_nodes(ctx->gbuf))
        return;

    const cbm_gbuf_node_t **method_nodes = NULL;
    int method_count = 0;
    cbm_gbuf_find_by_label(ctx->gbuf, "Method", (const cbm_gbuf_node_t ***)&method_nodes,
                           &method_count);
    if (method_count == 0)
        return;

    int n_calls = 0;

    for (int mi = 0; mi < method_count; mi++) {
        const cbm_gbuf_node_t *m = method_nodes[mi];
        if (!m->name || !m->file_path)
            continue;

        char full_path[CBM_SZ_1K];
        snprintf(full_path, sizeof(full_path), "%s/%s", ctx->repo_path, m->file_path);
        char *source = read_file(full_path);
        if (!source)
            continue;

        if (!strstr(source, "WorkMgr")) {
            free(source);
            continue;
        }

        const char *body_start = NULL, *body_end = NULL;
        if (!find_method_body(source, m->name, &body_start, &body_end)) {
            free(source);
            continue;
        }

        wm_target_t targets[MAX_QUEUE_TARGETS];
        int n = scan_workmgr_targets(body_start, body_end, targets, MAX_QUEUE_TARGETS);

        for (int ti = 0; ti < n; ti++) {
            const cbm_gbuf_node_t *target =
                resolve_target_method(ctx, targets[ti].class_qn, targets[ti].method_name);
            /* Unresolved targets (external or unindexed classes) emit nothing:
             * a class-level fallback would misstate what is actually called. */
            if (!target)
                continue;

            char conf_str[32];
            snprintf(conf_str, sizeof(conf_str), "%.2f", targets[ti].confidence);
            char props[CBM_SZ_512];
            snprintf(props, sizeof(props),
                     "{\"via\":\"workmgr_queue\",\"wm_method\":\"%s\",\"confidence\":%s}",
                     targets[ti].via, conf_str);
            cbm_gbuf_insert_edge(ctx->gbuf, m->id, target->id, "CALLS", props);
            n_calls++;
        }

        free(source);
    }

    char n_calls_buf[32], n_methods_buf[32];
    snprintf(n_calls_buf, sizeof(n_calls_buf), "%d", n_calls);
    snprintf(n_methods_buf, sizeof(n_methods_buf), "%d", method_count);
    cbm_log_info("workmgr_dispatch.done", "calls", n_calls_buf, "methods", n_methods_buf);
}
