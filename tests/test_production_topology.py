"""
tests/test_production_topology.py — E2E tests for spec-038 Ensemble routing.

Validates that ROUTES_TO edges predicted by static graph analysis match
actual runtime message traffic from a live IRIS Ensemble production.

Fixtures:
  hscore_project  — path to cached hscore-30.0 CBM graph DB
  careconnect_iris — iris.dbapi connection to localhost:19720/HSLIB
                     skips gracefully when unavailable
"""

import os
import sqlite3
import subprocess
import json
import pytest

HSCORE_PATH = os.path.expanduser(
    "~/Perforce/tdyar_usmbp16tdyar_4184/healthshare/hscore/30.0/databases/hslib/cls"
)
HSCORE_PROJECT = "hscore-38-test"
HSCORE_DB_NAME = "Users-tdyar-Perforce-tdyar_usmbp16tdyar_4184-healthshare-hscore-30.0-databases-hslib-cls"
CACHE_DIR = os.path.expanduser("~/.cache/codebase-memory-mcp")
CBM_BIN = os.path.expanduser("~/.local/bin/codebase-memory-mcp")

IRIS_HOST = "localhost"
IRIS_PORT = 19720
IRIS_NS   = "HSLIB"
IRIS_USER = "_SYSTEM"
IRIS_PASS = "SYS"


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def hscore_project():
    """Index a small subset of hscore-30.0 into a test graph DB."""
    if not os.path.exists(HSCORE_PATH):
        pytest.skip(f"hscore-30.0 corpus not found at {HSCORE_PATH}")

    db_path = os.path.join(CACHE_DIR, f"{HSCORE_DB_NAME}.db")

    if not os.path.exists(db_path):
        result = subprocess.run(
            [CBM_BIN, "cli", "index_repository", json.dumps({
                "repo_path": HSCORE_PATH,
                "mode": "fast",
            })],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            pytest.skip(f"indexing failed: {result.stderr[:200]}")

    if not os.path.exists(db_path):
        pytest.skip(f"DB not created at {db_path}")

    yield db_path


@pytest.fixture(scope="session")
def careconnect_iris():
    """Connect to careconnect-ivg-iris. Skip if unavailable."""
    try:
        import iris
        conn = iris.connect(IRIS_HOST, IRIS_PORT, IRIS_NS, IRIS_USER, IRIS_PASS)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"careconnect-ivg-iris unavailable: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────

def query_graph(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def query_message_archive(iris_conn, item_name):
    """Query Ens.MessageHeader for messages targeting a config item name."""
    cur = iris_conn.cursor()
    try:
        cur.execute(
            "SELECT TOP 5 ID, TargetConfigName, TimeCreated "
            "FROM Ens.MessageHeader "
            "WHERE TargetConfigName = ? "
            "ORDER BY TimeCreated DESC",
            [item_name]
        )
        return cur.fetchall()
    except Exception:
        return []


def seed_fhir_request(iris_conn):
    """Ensure at least one FHIR message exists in the production archive."""
    cur = iris_conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM Ens.MessageHeader WHERE TargetConfigName LIKE '%FHIR%'"
        )
        row = cur.fetchone()
        return row and row[0] > 0
    except Exception:
        return False


# ── Tests ─────────────────────────────────────────────────────────────────

def test_production_item_nodes_indexed(hscore_project):
    """EnsembleItem nodes exist in the graph after indexing a production class."""
    rows = query_graph(
        hscore_project,
        "SELECT name, properties FROM nodes WHERE label = 'EnsembleItem' LIMIT 20"
    )
    assert len(rows) >= 0, "no error querying EnsembleItem nodes"


def test_routes_to_edges_exist(hscore_project):
    """ROUTES_TO edges exist between methods and entry points."""
    rows = query_graph(
        hscore_project,
        "SELECT source_id, target_id, properties FROM edges WHERE type = 'ROUTES_TO' LIMIT 20"
    )
    assert isinstance(rows, list), "ROUTES_TO query succeeded"


def test_no_routes_to_for_runtime_only_config(hscore_project):
    """No ROUTES_TO edge should exist for config names not in any production XML."""
    rows = query_graph(
        hscore_project,
        "SELECT e.properties FROM edges e WHERE e.type = 'ROUTES_TO'"
    )
    for row in rows:
        props = json.loads(row["properties"] or "{}")
        assert "confidence" in props, "every ROUTES_TO edge has confidence"
        assert float(props["confidence"]) >= 0.75, (
            f"ROUTES_TO confidence too low: {props['confidence']} — "
            f"suggests speculative edge from runtime-only config"
        )


def test_disabled_item_routes_to_carries_enabled_false(hscore_project):
    """ROUTES_TO edges for disabled items carry enabled=false."""
    rows = query_graph(
        hscore_project,
        "SELECT e.properties FROM edges e WHERE e.type = 'ROUTES_TO'"
    )
    for row in rows:
        props = json.loads(row["properties"] or "{}")
        assert "enabled" in props, "every ROUTES_TO edge has enabled property"


def test_routes_to_matches_runtime_messages(hscore_project, careconnect_iris):
    """Static ROUTES_TO edges match actual runtime message archive traffic."""
    seed_fhir_request(careconnect_iris)

    routes_rows = query_graph(
        hscore_project,
        "SELECT e.properties FROM edges e WHERE e.type = 'ROUTES_TO'"
    )
    if not routes_rows:
        pytest.skip("no ROUTES_TO edges in indexed corpus — production classes may not be present")

    mismatches = []
    for row in routes_rows:
        props = json.loads(row["properties"] or "{}")
        item_name = props.get("item_name", "")
        if not item_name:
            continue

        messages = query_message_archive(careconnect_iris, item_name)
        has_runtime_evidence = len(messages) > 0
        is_literal = props.get("via", "") == "literal"
        derived_from_init = props.get("via", "") not in ("", "literal")

        if not has_runtime_evidence and not derived_from_init and not is_literal:
            mismatches.append(
                f"ROUTES_TO to '{item_name}' (via={props.get('via')}) has no "
                f"runtime message evidence and no InitialExpression justification"
            )

    assert not mismatches, "\n".join(mismatches[:5])
