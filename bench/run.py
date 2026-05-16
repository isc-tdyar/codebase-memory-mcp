#!/usr/bin/env python3
"""
CBM ObjectScript Feature Progression Benchmark
===============================================
Builds a binary at each milestone commit, indexes the same corpus with each,
and records graph metrics (node/edge counts) per run.

Results saved to bench/results.json + bench/results.csv.

Usage:
    python3 bench/run.py [--corpus PATH] [--skip-build]

Requirements:
    - Run from the repo root: /Users/tdyar/ws/codebase-memory-mcp
    - Makefile.cbm must be present
    - The CLI binary supports: cli index_repository + cli query_graph

Config lives in bench/config.json (auto-created if missing).
"""

import subprocess, json, os, sys, csv, time, shutil
from pathlib import Path

REPO = Path(__file__).parent.parent.resolve()
BENCH = REPO / "bench"
RESULTS_JSON = BENCH / "results.json"
RESULTS_CSV  = BENCH / "results.csv"
CONFIG_FILE  = BENCH / "config.json"
BINARIES_DIR = BENCH / "binaries"

# ---------------------------------------------------------------------------
# Default config — edit bench/config.json to override
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "corpus": "/Users/tdyar/Perforce/tdyar_usmbp16tdyar_4184/healthshare/hscm/15.x",
    "cbm_cache_base": "/tmp/cbm_bench",
    "milestones": [
        {"id": "m00-upstream-base",    "commit": "01c97eb", "label": "Upstream baseline (no ObjectScript)"},
        {"id": "m01-001-udl-grammar",  "commit": "b60a571", "label": "001 — UDL grammar"},
        {"id": "m02-004-calls-static", "commit": "372a2c3", "label": "004 — Static CALLS ##class()"},
        {"id": "m03-005-calls-deep",   "commit": "bbcc73f", "label": "005 — Deep CALLS ($$$macro + .INT)"},
        {"id": "m04-009-all-pre-010",  "commit": "00b7376", "label": "009 — All pre-010 features"},
        {"id": "m05-010-type-infer",   "commit": "4ecbbd2", "label": "010 — Type inference (Set x=%New)"},
        {"id": "m06-013-011-012-013",  "commit": None,      "label": "013 — Macros+ReturnTypes+DATA_FLOWS (HEAD)"}
    ],
    "queries": {
        "classes":    "MATCH (n:Class) RETURN count(n)",
        "methods":    "MATCH (n:Method) RETURN count(n)",
        "variables":  "MATCH (n:Variable) RETURN count(n)",
        "indexes":    "MATCH (n:Index) RETURN count(n)",
        "xdata":      "MATCH (n:XData) RETURN count(n)",
        "storage":    "MATCH (n:Storage) RETURN count(n)",
        "calls":      "MATCH ()-[r:CALLS]->() RETURN count(r)",
        "inherits":   "MATCH ()-[r:INHERITS]->() RETURN count(r)",
        "data_flows": "MATCH ()-[r:DATA_FLOWS]->() RETURN count(r)"
    }
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        # Merge missing keys from DEFAULT_CONFIG
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"Created default config: {CONFIG_FILE}")
        return DEFAULT_CONFIG

def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

def git_checkout(commit):
    r = run(["git", "checkout", commit], cwd=REPO, env={**os.environ, "GIT_PAGER": "cat"})
    if r.returncode != 0:
        raise RuntimeError(f"git checkout {commit} failed:\n{r.stderr}")

def build_binary(milestone_id):
    binary_path = BINARIES_DIR / milestone_id
    if binary_path.exists():
        print(f"  [skip] binary already exists: {binary_path}")
        return binary_path
    r = run(["make", "-j16", "-f", "Makefile.cbm", "cbm"], cwd=REPO)
    if r.returncode != 0:
        raise RuntimeError(f"make failed:\n{r.stderr[-2000:]}")
    src = REPO / "build/c/codebase-memory-mcp"
    shutil.copy2(src, binary_path)
    print(f"  [built] {binary_path}")
    return binary_path

def get_project_name(binary, corpus, cache_dir):
    r = run([str(binary), "cli", "list_projects"],
            env={**os.environ, "CBM_CACHE_DIR": str(cache_dir)})
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
            projects = d.get("projects", [])
            if projects:
                return projects[0]["name"]
        except Exception:
            pass
    corpus_str = str(corpus).lstrip("/").replace("/", "-")
    return corpus_str

def index_corpus(binary, corpus, cache_dir):
    """Run indexing. Returns (elapsed_s, log_lines)."""
    t0 = time.time()
    r = run([str(binary), "cli", "index_repository",
             json.dumps({"repo_path": str(corpus), "mode": "full"})],
            env={**os.environ, "CBM_CACHE_DIR": str(cache_dir)})
    elapsed = time.time() - t0
    return elapsed, r.stdout + r.stderr

def query_metric(binary, project, query, cache_dir):
    r = run([str(binary), "cli", "query_graph",
             json.dumps({"query": query, "project": project})],
            env={**os.environ, "CBM_CACHE_DIR": str(cache_dir)})
    try:
        d = json.loads(r.stdout)
        rows = d.get("rows", [])
        return int(rows[0][0]) if rows else 0
    except Exception:
        return -1

def run_benchmark(skip_build=False):
    cfg = load_config()
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    corpus = Path(cfg["corpus"])
    cache_base = Path(cfg["cbm_cache_base"])
    milestones = cfg["milestones"]
    queries = cfg["queries"]

    results = []

    for ms in milestones:
        ms_id   = ms["id"]
        commit  = ms["commit"]   # None = current HEAD
        label   = ms["label"]
        cache_dir = cache_base / ms_id

        print(f"\n{'='*60}")
        print(f"  {ms_id}: {label}")
        print(f"  commit: {commit or 'HEAD'}")
        print(f"{'='*60}")

        # --- Build ---
        if not skip_build:
            if commit:
                git_checkout(commit)
            else:
                print("  [using current HEAD]")
            binary = build_binary(ms_id)
        else:
            binary = BINARIES_DIR / ms_id
            if not binary.exists():
                print(f"  [SKIP] no binary found for {ms_id}")
                continue

        # --- Index ---
        print(f"  Indexing {corpus} ...")
        elapsed, log = index_corpus(binary, corpus, cache_dir)
        print(f"  Indexed in {elapsed:.1f}s")

        # --- Derive project name ---
        project = get_project_name(binary, corpus, cache_dir)

        # --- Query metrics ---
        metrics = {"elapsed_s": round(elapsed, 1)}
        for key, cypher in queries.items():
            val = query_metric(binary, project, cypher, cache_dir)
            metrics[key] = val
            print(f"    {key:12s} = {val}")

        row = {"id": ms_id, "label": label, "commit": commit or "HEAD", **metrics}
        results.append(row)

        # Save incrementally
        with open(RESULTS_JSON, "w") as f:
            json.dump(results, f, indent=2)

    # Save CSV
    if results:
        fieldnames = ["id", "label", "commit"] + list(queries.keys()) + ["elapsed_s"]
        with open(RESULTS_CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(results)
        print(f"\nResults saved to:\n  {RESULTS_JSON}\n  {RESULTS_CSV}")

    # Restore to original branch if we checked out commits
    if not skip_build:
        run(["git", "checkout", "-"], cwd=REPO,
            env={**os.environ, "GIT_PAGER": "cat"})

    return results

if __name__ == "__main__":
    skip_build = "--skip-build" in sys.argv
    results = run_benchmark(skip_build=skip_build)
    print("\nDone.")
