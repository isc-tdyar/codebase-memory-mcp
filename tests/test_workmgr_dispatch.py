"""tests/test_workmgr_dispatch.py — integration tests for spec-039 WorkMgr queue dispatch.

Indexes a synthetic ObjectScript corpus containing WorkMgr .Queue("##class(X).method", ...)
patterns and verifies that CALLS edges are created with via=WorkMgr.Queue.
"""

import os, subprocess, json, sqlite3, pytest

CBM_BIN = os.path.expanduser("~/.local/bin/codebase-memory-mcp")
CACHE_DIR = os.path.expanduser("~/.cache/codebase-memory-mcp")
CORPUS_DIR = "/tmp/cbm_workmgr_test"


@pytest.fixture(scope="session", autouse=True)
def workmgr_corpus(tmp_path_factory):
    import tempfile, pathlib
    corpus = pathlib.Path(CORPUS_DIR)
    corpus.mkdir(parents=True, exist_ok=True)

    (corpus / "Worker.cls").write_text("""\
Class Test.Worker
{

ClassMethod populateCacheTask(pSession As %Integer) As %Status
{
    Set tObj = ##class(Test.Data).%OpenId(pSession)
    Quit $$$OK
}

ClassMethod otherTask() As %Status
{
    Quit $$$OK
}

}
""")

    (corpus / "Dispatcher.cls").write_text("""\
Class Test.Dispatcher
{

Method dispatch(pSession As %Integer) As %Status
{
    Set tQueue = $system.WorkMgr.Initialize("/multicompile=1", .tSC)
    Set tSC = tQueue.Queue("##class(Test.Worker).populateCacheTask", pSession)
    Set tSC = tQueue.WaitForComplete()
    Quit tSC
}

Method nonDispatch() As %Status
{
    Set count = ##class(Ens.Queue).GetCount("myqueue")
    Quit $$$OK
}

}
""")
    db = os.path.join(CACHE_DIR, "tmp-cbm_workmgr_test.db")
    os.remove(db) if os.path.exists(db) else None
    result = subprocess.run(
        [CBM_BIN, "cli", "index_repository", json.dumps({
            "repo_path": CORPUS_DIR, "mode": "full"
        })],
        capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"indexing failed: {result.stderr[:300]}"
    assert os.path.exists(db), f"DB not created at {db}"
    yield db


def query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_workmgr_calls_edge_exists(workmgr_corpus):
    rows = query(workmgr_corpus, """
        SELECT src.name as from_meth, tgt.name as to_meth,
               json_extract(e.properties,'$.via') as via,
               json_extract(e.properties,'$.confidence') as conf
        FROM edges e
        JOIN nodes src ON e.source_id = src.id
        JOIN nodes tgt ON e.target_id = tgt.id
        WHERE e.type = 'CALLS'
          AND json_extract(e.properties,'$.via') = 'WorkMgr.Queue'
    """)
    assert len(rows) >= 1, "expected at least one WorkMgr.Queue CALLS edge"
    r = rows[0]
    assert r["from_meth"] == "dispatch"
    assert r["to_meth"] == "populateCacheTask"
    assert float(r["conf"]) == pytest.approx(0.90)


def test_workmgr_calls_confidence(workmgr_corpus):
    rows = query(workmgr_corpus, """
        SELECT json_extract(e.properties,'$.confidence') as conf
        FROM edges e
        WHERE e.type = 'CALLS'
          AND json_extract(e.properties,'$.via') = 'WorkMgr.Queue'
    """)
    for r in rows:
        assert float(r["conf"]) == pytest.approx(0.90), \
            f"WorkMgr.Queue CALLS edge should have confidence 0.90, got {r['conf']}"


def test_no_false_positive_ens_queue(workmgr_corpus):
    rows = query(workmgr_corpus, """
        SELECT e.properties FROM edges e
        JOIN nodes src ON e.source_id = src.id
        WHERE e.type = 'CALLS' AND src.name = 'nonDispatch'
          AND json_extract(e.properties,'$.via') = 'WorkMgr.Queue'
    """)
    assert len(rows) == 0, \
        "Ens.Queue.GetCount() should NOT produce a WorkMgr.Queue CALLS edge"


def test_trace_path_crosses_workmgr(workmgr_corpus):
    result = subprocess.run(
        [CBM_BIN, "cli", "trace_path", json.dumps({
            "function_name": "dispatch",
            "project": "tmp-cbm_workmgr_test",
            "direction": "outbound",
            "depth": 2,
            "mode": "calls"
        })],
        capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0
    d = json.loads(result.stdout)
    callees = [c["name"] for c in d.get("callees", [])]
    assert "populateCacheTask" in callees, \
        f"trace_path should reach populateCacheTask via WorkMgr.Queue edge; got {callees}"
