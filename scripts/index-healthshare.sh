#!/usr/bin/env bash
# =============================================================================
# index-healthshare.sh
#
# Indexes the HealthShare P4 depot with codebase-memory-mcp.
# Written for Tom Dyar's fork: github.com/isc-tdyar/codebase-memory-mcp
#
# PREREQUISITES
# -------------
# 1. Install the binary:
#    a) Clone the fork:  git clone https://github.com/isc-tdyar/codebase-memory-mcp
#    b) Build:           cd codebase-memory-mcp && make -j$(nproc) -f Makefile.cbm cbm
#    c) macOS only — sign the binary (required or it gets SIGKILL):
#                        codesign --sign - --force build/c/codebase-memory-mcp
#    d) Copy to PATH:    cp build/c/codebase-memory-mcp ~/.local/bin/codebase-memory-mcp
#
#    Or run the install script if available:  cbm-install
#
# 2. Set P4_BASE to your local Perforce client root for the healthshare depot.
#
# USAGE
# -----
#    ./index-healthshare.sh
#    ./index-healthshare.sh --force     # delete cached DBs first (full re-index)
#    ./index-healthshare.sh --parallel  # run all components at once (uses more RAM)
#
# WHAT GETS INDEXED
# -----------------
#    Only the ObjectScript source trees:
#      */latest/databases/*/cls/    (.cls  .inc  .xml Export files)
#
#    Excluded intentionally:
#      - Older version branches (12.x 13.x 14.x etc.)
#      - UI layers (JavaScript, Python, compiled assets)
#      - Build artifacts, documentation, test infra
#
# WHERE RESULTS GO
# ----------------
#    ~/.cache/codebase-memory-mcp/<project-name>.db  (one SQLite DB per component)
#
# HOW TO QUERY AFTER INDEXING
# ---------------------------
#    See QUERYING.md or run:
#      codebase-memory-mcp cli list_projects
#      codebase-memory-mcp cli query_graph '{"query":"MATCH (n:Class) RETURN count(n)","project":"..."}'
#
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

P4_BASE="${P4_BASE:-/Users/tdyar/Perforce/tdyar_usmbp16tdyar_4184/healthshare}"
CBM="${CBM:-$HOME/.local/bin/codebase-memory-mcp}"
CBM_CACHE="${CBM_CACHE_DIR:-$HOME/.cache/codebase-memory-mcp}"
FORCE=0
PARALLEL=0
LOG_DIR="/tmp/cbm-hs-index-logs"

for arg in "$@"; do
  case "$arg" in
    --force)    FORCE=1 ;;
    --parallel) PARALLEL=1 ;;
  esac
done

# ── Components to index ───────────────────────────────────────────────────────
#
# Each entry: "<component>:<latest-path>"
# All paths are relative to P4_BASE and point to the root of the source tree
# (not just the cls/ subdirectory — the binary discovers .cls/.inc/.xml inside).
#
# Components with ObjectScript source at latest/:
COMPONENTS=(
  "hsaa:hsaa/latest"
  "hscm:hscm/latest"
  "hscommunity:hscommunity/latest"
  "hscore:hscore/latest"
  "hseds:hseds/latest"
  "hspd:hspd/latest"
  "hspi:hspi/latest"
  "hsviewer:hsviewer/latest"
)

# NOTE on hsviewer: contains ~17,700 IRIS Export XML files with
# generator="IRIS" (not "Cache"). The current binary only parses
# generator="Cache" exports. Those files are indexed as XML but their
# ObjectScript content is not extracted — this is a known gap.

# ── Sanity checks ─────────────────────────────────────────────────────────────

if [ ! -f "$CBM" ]; then
  echo "ERROR: codebase-memory-mcp not found at $CBM"
  echo "       Set CBM=/path/to/binary or install to ~/.local/bin/"
  exit 1
fi

if [ ! -d "$P4_BASE" ]; then
  echo "ERROR: P4_BASE not found: $P4_BASE"
  echo "       Set P4_BASE=/path/to/your/healthshare/depot"
  exit 1
fi

mkdir -p "$LOG_DIR"

# ── Main ──────────────────────────────────────────────────────────────────────

echo "codebase-memory-mcp: $($CBM --version 2>/dev/null || echo 'version unknown')"
echo "P4 depot:  $P4_BASE"
echo "Cache dir: $CBM_CACHE"
echo "Mode:      $( [ $FORCE -eq 1 ] && echo 'FORCE (delete existing DBs)' || echo 'incremental' )"
echo "Parallel:  $( [ $PARALLEL -eq 1 ] && echo 'yes (all at once)' || echo 'no (sequential)' )"
echo ""

PIDS=()
STARTED=0
FAILED=0

index_component() {
  local name="$1"
  local relpath="$2"
  local abs_path="$P4_BASE/$relpath"
  local logfile="$LOG_DIR/${name}.log"

  if [ ! -d "$abs_path" ]; then
    echo "  SKIP $name — path not found: $abs_path"
    return
  fi

  local cls_count
  cls_count=$(find "$abs_path" -name "*.cls" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$cls_count" -eq 0 ]; then
    echo "  SKIP $name — no .cls files found"
    return
  fi

  if [ $FORCE -eq 1 ]; then
    local db_name
    db_name=$(echo "$abs_path" | sed 's|/|-|g' | sed 's|^-||')
    local db_path="$CBM_CACHE/${db_name}.db"
    if [ -f "$db_path" ]; then
      rm -f "$db_path"
      echo "  Deleted cached DB for $name"
    fi
  fi

  echo "  Indexing $name ($cls_count .cls files) → $logfile"

  CBM_CACHE_DIR="$CBM_CACHE" "$CBM" cli index_repository \
    "{\"repo_path\":\"$abs_path\",\"mode\":\"full\"}" \
    > "$logfile" 2>&1
}

index_component_bg() {
  local name="$1"
  local relpath="$2"
  local abs_path="$P4_BASE/$relpath"
  local logfile="$LOG_DIR/${name}.log"

  if [ ! -d "$abs_path" ]; then
    echo "  SKIP $name — path not found"
    return
  fi

  local cls_count
  cls_count=$(find "$abs_path" -name "*.cls" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$cls_count" -eq 0 ]; then
    echo "  SKIP $name — no .cls files found"
    return
  fi

  if [ $FORCE -eq 1 ]; then
    local db_name
    db_name=$(echo "$abs_path" | sed 's|/|-|g' | sed 's|^-||')
    local db_path="$CBM_CACHE/${db_name}.db"
    rm -f "$db_path" 2>/dev/null
  fi

  echo "  Launching $name ($cls_count .cls files) → $logfile"
  CBM_CACHE_DIR="$CBM_CACHE" "$CBM" cli index_repository \
    "{\"repo_path\":\"$abs_path\",\"mode\":\"full\"}" \
    > "$logfile" 2>&1 &
  PIDS+=($!)
  STARTED=$((STARTED + 1))
}

if [ $PARALLEL -eq 1 ]; then
  echo "Launching all components in parallel..."
  for entry in "${COMPONENTS[@]}"; do
    IFS=':' read -r name relpath <<< "$entry"
    index_component_bg "$name" "$relpath"
  done

  echo ""
  echo "Waiting for ${#PIDS[@]} jobs..."
  for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
      FAILED=$((FAILED + 1))
    fi
  done
else
  echo "Indexing sequentially..."
  STARTED=${#COMPONENTS[@]}
  for entry in "${COMPONENTS[@]}"; do
    IFS=':' read -r name relpath <<< "$entry"
    index_component "$name" "$relpath" || FAILED=$((FAILED + 1))
  done
fi

# ── Results ───────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════"
echo "Results"
echo "═══════════════════════════════════════"

for entry in "${COMPONENTS[@]}"; do
  IFS=':' read -r name relpath <<< "$entry"
  logfile="$LOG_DIR/${name}.log"
  if [ ! -f "$logfile" ]; then
    echo "  $name: skipped"
    continue
  fi
  result=$(grep '"status"' "$logfile" 2>/dev/null | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if line.startswith('{'):
        try:
            d = json.loads(line)
            if 'nodes' in d:
                print(f'nodes={d[\"nodes\"]:,}  edges={d[\"edges\"]:,}')
        except: pass
" 2>/dev/null)
  if [ -n "$result" ]; then
    echo "  $name: $result"
  else
    last=$(tail -1 "$logfile" 2>/dev/null | head -c 100)
    echo "  $name: FAILED or still running — last log: $last"
  fi
done

echo ""
if [ $FAILED -eq 0 ]; then
  echo "All done. Query with:"
  echo "  $CBM cli list_projects"
else
  echo "WARNING: $FAILED component(s) failed. Check logs in $LOG_DIR/"
fi
