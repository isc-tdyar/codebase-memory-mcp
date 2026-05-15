#include "pipeline/pass_iris_dict.h"
#include "graph_buffer/graph_buffer.h"
#include "foundation/log.h"
#include "foundation/constants.h"
#include <yyjson/yyjson.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    IRIS_DICT_LINE_MAX  = 65536,
    IRIS_DICT_PATH_MAX  = 4096,
    IRIS_DICT_PROPS_MAX = 1024,
};

static const char *jstr(yyjson_val *root, const char *key) {
    yyjson_val *v = yyjson_obj_get(root, key);
    if (!v || !yyjson_is_str(v)) { return ""; }
    return yyjson_get_str(v);
}

static bool jbool(yyjson_val *root, const char *key) {
    yyjson_val *v = yyjson_obj_get(root, key);
    return v && yyjson_is_bool(v) && yyjson_get_bool(v);
}

static void build_props(char *buf, size_t bufsz, yyjson_val *root,
                        const char **keys, int nkeys) {
    size_t pos = 0;
    pos += (size_t)snprintf(buf + pos, bufsz - pos, "{");
    int wrote = 0;
    for (int i = 0; i < nkeys; i++) {
        const char *v = jstr(root, keys[i]);
        if (!v || !v[0]) { continue; }
        if (wrote) { pos += (size_t)snprintf(buf + pos, bufsz - pos, ","); }
        pos += (size_t)snprintf(buf + pos, bufsz - pos, "\"%s\":\"%s\"", keys[i], v);
        wrote++;
    }
    snprintf(buf + pos, bufsz - pos, "}");
}

static void process_line(cbm_iris_dict_cfg_t *cfg, const char *line) {
    yyjson_doc *doc = yyjson_read(line, strlen(line), 0);
    if (!doc) { return; }
    yyjson_val *root = yyjson_doc_get_root(doc);

    const char *type    = jstr(root, "type");
    const char *cls     = jstr(root, "class");
    const char *name    = jstr(root, "name");
    const char *project = cfg->project_name ? cfg->project_name : "";

    if (strcmp(type, "done") == 0) {
        yyjson_doc_free(doc);
        return;
    }
    if (strcmp(type, "error") == 0) {
        cbm_log_warn("iris_dict.error", "message", jstr(root, "message"));
        yyjson_doc_free(doc);
        return;
    }

    char qn[CBM_SZ_256];
    char props[IRIS_DICT_PROPS_MAX];

    if (strcmp(type, "class") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s", project, name);
        static const char *class_keys[] = {"super", "description", NULL};
        build_props(props, sizeof(props), root, class_keys, 2);
        cbm_gbuf_upsert_node(cfg->gbuf, "Class", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "inherits") == 0) {
        const char *child  = jstr(root, "child");
        const char *parent = jstr(root, "parent");
        char child_qn[CBM_SZ_256], parent_qn[CBM_SZ_256];
        snprintf(child_qn,  sizeof(child_qn),  "%s.%s", project, child);
        snprintf(parent_qn, sizeof(parent_qn), "%s.%s", project, parent);
        int64_t child_id  = cbm_gbuf_upsert_node(cfg->gbuf, "Class", child,  child_qn,  "", 0, 0, "{}");
        int64_t parent_id = cbm_gbuf_upsert_node(cfg->gbuf, "Class", parent, parent_qn, "", 0, 0, "{}");
        if (child_id > 0 && parent_id > 0) {
            cbm_gbuf_insert_edge(cfg->gbuf, child_id, parent_id, "INHERITS", "{}");
        }

    } else if (strcmp(type, "method") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *meth_keys[] = {"return_type", "formal_spec", "description", NULL};
        build_props(props, sizeof(props), root, meth_keys, 3);
        if (jbool(root, "class_method")) {
            cbm_gbuf_upsert_node(cfg->gbuf, "Method", name, qn, "", 0, 0, props);
        } else {
            cbm_gbuf_upsert_node(cfg->gbuf, "Method", name, qn, "", 0, 0, props);
        }

    } else if (strcmp(type, "property") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *prop_keys[] = {"prop_type", "collection", "description", NULL};
        build_props(props, sizeof(props), root, prop_keys, 3);
        cbm_gbuf_upsert_node(cfg->gbuf, "Variable", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "parameter") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *par_keys[] = {"param_type", "default", "description", NULL};
        build_props(props, sizeof(props), root, par_keys, 3);
        cbm_gbuf_upsert_node(cfg->gbuf, "Variable", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "query") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *qry_keys[] = {"sql_name", "query_type", "formal_spec", "description", NULL};
        build_props(props, sizeof(props), root, qry_keys, 4);
        cbm_gbuf_upsert_node(cfg->gbuf, "Function", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "xdata") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *xd_keys[] = {"mime_type", "schema_spec", NULL};
        build_props(props, sizeof(props), root, xd_keys, 2);
        cbm_gbuf_upsert_node(cfg->gbuf, "XData", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "trigger") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *trig_keys[] = {"event", "foreach", "description", NULL};
        build_props(props, sizeof(props), root, trig_keys, 3);
        cbm_gbuf_upsert_node(cfg->gbuf, "Trigger", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "index") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *idx_keys[] = {"properties", "index_type", NULL};
        build_props(props, sizeof(props), root, idx_keys, 2);
        cbm_gbuf_upsert_node(cfg->gbuf, "Index", name, qn, "", 0, 0, props);

    } else if (strcmp(type, "storage") == 0) {
        snprintf(qn, sizeof(qn), "%s.%s.%s", project, cls, name);
        static const char *sto_keys[] = {"storage_type", NULL};
        build_props(props, sizeof(props), root, sto_keys, 1);
        cbm_gbuf_upsert_node(cfg->gbuf, "Storage", name, qn, "", 0, 0, props);
    }

    yyjson_doc_free(doc);
}

int pass_iris_dict_run(cbm_iris_dict_cfg_t *cfg) {
    if (!cfg || !cfg->iris_host || !cfg->iris_host[0]) { return 0; }

    char extractor_path[IRIS_DICT_PATH_MAX];

    /* Find the extractor script relative to the binary */
    char self_path[IRIS_DICT_PATH_MAX] = {0};
#ifdef __APPLE__
    {
        uint32_t sz = sizeof(self_path);
        _NSGetExecutablePath(self_path, &sz);
    }
#elif defined(_WIN32)
    GetModuleFileNameA(NULL, self_path, sizeof(self_path));
#else
    {
        ssize_t n = readlink("/proc/self/exe", self_path, sizeof(self_path) - 1);
        if (n > 0) { self_path[n] = '\0'; }
    }
#endif

    if (self_path[0]) {
        char *slash = strrchr(self_path, '/');
        if (!slash) { slash = strrchr(self_path, '\\'); }
        if (slash) { *slash = '\0'; }
        snprintf(extractor_path, sizeof(extractor_path),
                 "%s/tools/iris_dict_extractor.py", self_path);
    } else {
        snprintf(extractor_path, sizeof(extractor_path), "tools/iris_dict_extractor.py");
    }

    const char *pkg = cfg->iris_package_filter ? cfg->iris_package_filter : "";
    char cmd[IRIS_DICT_PATH_MAX * 2];
    int cx = snprintf(cmd, sizeof(cmd),
             "env PATH=\"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin\" python3 -u \"%s\""
             " --host \"%s\" --port %d"
             " --namespace \"%s\" --user \"%s\" --pass \"%s\""
             " --package \"",
             extractor_path,
             cfg->iris_host, cfg->iris_port > 0 ? cfg->iris_port : 1972,
             cfg->iris_namespace ? cfg->iris_namespace : "USER",
             cfg->iris_user      ? cfg->iris_user      : "_SYSTEM",
             cfg->iris_pass      ? cfg->iris_pass      : "");
    for (int i = 0; pkg[i] && cx < (int)sizeof(cmd) - 16; i++) {
        cmd[cx++] = pkg[i];
    }
    cmd[cx] = '\0';
    strncat(cmd, "\" 2>/dev/null", sizeof(cmd) - (size_t)cx - 1);

    cbm_log_info("iris_dict.start", "host", cfg->iris_host,
                 "namespace", cfg->iris_namespace ? cfg->iris_namespace : "USER");

    FILE *pipe = popen(cmd, "r");
    if (!pipe) {
        cbm_log_warn("iris_dict.popen_failed");
        return 0;
    }

    char line[IRIS_DICT_LINE_MAX];
    while (fgets(line, sizeof(line), pipe)) {
        size_t len = strlen(line);
        while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) {
            line[--len] = '\0';
        }
        if (len > 0) { process_line(cfg, line); }
    }

    int status = pclose(pipe);
    if (status != 0) {
        cbm_log_warn("iris_dict.extractor_nonzero_exit");
    } else {
        cbm_log_info("iris_dict.done");
    }
    return 0;
}
