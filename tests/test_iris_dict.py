import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock

EXTRACTOR = Path(__file__).parent.parent / "tools" / "iris_dict_extractor.py"

_spec_cache = {}


def _load_extractor():
    import importlib.util
    if "ext" not in _spec_cache:
        spec = importlib.util.spec_from_file_location("iris_dict_extractor", EXTRACTOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _spec_cache["ext"] = mod
    return _spec_cache["ext"]


def _run_extract(conn, package="", exclude_system=True):
    mod = _load_extractor()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.extract(conn, package, exclude_system)
    return [json.loads(l) for l in buf.getvalue().splitlines() if l.strip()]


def run_extractor(*args):
    cmd = [sys.executable, str(EXTRACTOR)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    return result.returncode, lines, result.stderr


class TestNdjsonOutputFormat:

    def test_all_records_are_valid_json(self):
        conn = _make_conn()
        records = _run_extract(conn)
        assert len(records) > 0
        for r in records:
            assert "type" in r

    def test_done_record_is_last(self):
        conn = _make_conn()
        records = _run_extract(conn)
        last = records[-1]
        assert last["type"] == "done"
        assert "count" in last


class TestClassFilter:

    def test_package_filter_excludes_system_classes(self):
        conn = _make_conn(classes=[
            ("MyApp.Patient", "%Persistent", False, ""),
            ("%Library.RegisteredObject", "%Library.Base", False, ""),
        ])
        records = _run_extract(conn, package="MyApp")
        class_names = [r["name"] for r in records if r["type"] == "class"]
        assert "MyApp.Patient" in class_names
        assert "%Library.RegisteredObject" not in class_names


class TestConnectionFailure:

    def test_bad_host_exits_nonzero(self):
        rc, _, _ = run_extractor(
            "--host", "255.255.255.255", "--port", "1972",
            "--namespace", "USER", "--user", "_SYSTEM", "--pass", "SYS",
        )
        assert rc != 0

    def test_bad_host_emits_error_to_stderr(self):
        _, _, stderr = run_extractor(
            "--host", "255.255.255.255", "--port", "1972",
            "--namespace", "USER", "--user", "_SYSTEM", "--pass", "SYS",
        )
        assert len(stderr) > 0


class TestMultiParentExtends:

    def test_multi_parent_emits_multiple_inherits(self):
        conn = _make_conn(classes=[("MyApp.Multi", "Base.A,Base.B,Base.C", False, "")])
        records = _run_extract(conn)
        inherits = [r for r in records if r["type"] == "inherits" and r["child"] == "MyApp.Multi"]
        parents = {r["parent"] for r in inherits}
        assert parents == {"Base.A", "Base.B", "Base.C"}


class TestAllMemberTypes:

    def test_member_type_records(self):
        conn = _make_conn(
            classes=[("MyApp.Full", "%Persistent", False, "")],
            methods=[("MyApp.Full", "Save", "%Status", False, "", "")],
            properties=[("MyApp.Full", "Name", "%String", "", "")],
            parameters=[("MyApp.Full", "DOMAIN", "%String", "MyApp", "")],
            queries=[("MyApp.Full", "FindAll", "FindAll", "%Query", "", "")],
            indices=[("MyApp.Full", "NameIdx", "Name", False, "index")],
            xdatas=[("MyApp.Full", "MyXData", "application/json", "")],
            triggers=[("MyApp.Full", "AfterSave", "INSERT", "row/object", "")],
        )
        records = _run_extract(conn)
        types_found = {r["type"] for r in records}
        for expected in ["class", "method", "property", "parameter",
                         "query", "index", "xdata", "trigger"]:
            assert expected in types_found, f"Missing: {expected}. Found: {types_found}"


def _make_conn(classes=None, methods=None, properties=None, parameters=None,
               queries=None, indices=None, xdatas=None, triggers=None, storages=None):
    if classes is None:
        classes = [("%Library.RegisteredObject", "%Library.Base", False, "")]

    data = {
        "ClassDefinition": classes or [],
        "MethodDefinition": methods or [],
        "PropertyDefinition": properties or [],
        "ParameterDefinition": parameters or [],
        "QueryDefinition": queries or [],
        "IndexDefinition": indices or [],
        "XDataDefinition": xdatas or [],
        "TriggerDefinition": triggers or [],
        "StorageDefinition": storages or [],
    }

    class FakeCursor:
        def __init__(self):
            self._rows = []

        def execute(self, sql, params=None):
            self._rows = []
            for fragment, rows in data.items():
                if fragment in sql:
                    self._rows = list(rows)
                    break

        def fetchall(self):
            return list(self._rows)

        def fetchmany(self, size=1000):
            return list(self._rows)

    class FakeConn:
        def cursor(self):
            return FakeCursor()
        def close(self):
            pass

    return FakeConn()
