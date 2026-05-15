"""iris_dict_extractor.py — extract %Dictionary structural data from IRIS.

Streams newline-delimited JSON to stdout. One record per line.
Final record: {"type":"done","count":N}
Errors go to stderr as {"type":"error","message":"..."}, exit 1.

Usage:
    python3 iris_dict_extractor.py --host localhost --port 1972 \
        --namespace USER --user _SYSTEM --pass SYS [--package HS.FHIRServer]
"""

import argparse
import json
import sys


def emit(record):
    print(json.dumps(record, ensure_ascii=False), flush=True)


def emit_error(msg):
    print(json.dumps({"type": "error", "message": msg}), file=sys.stderr, flush=True)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1972)
    p.add_argument("--namespace", default="USER")
    p.add_argument("--user", default="_SYSTEM")
    p.add_argument("--pass", dest="password", default="SYS")
    p.add_argument("--package", default="")
    p.add_argument("--exclude-system", action="store_true", default=True)
    return p.parse_args()


def make_filter(package, exclude_system):
    parts = []
    if package:
        parts.append(f"Name %STARTSWITH '{package}'")
    if exclude_system and not package:
        parts.append("Name NOT LIKE '$%'")
    return " AND ".join(parts) if parts else "1=1"


def safe_str(v):
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return "<binary>"


def extract(conn, package, exclude_system):
    cursor = conn.cursor()
    count = 0

    where = make_filter(package, exclude_system)
    cursor.execute(
        f"SELECT Name, Super, Abstract, Description "
        f"FROM %Dictionary.ClassDefinition WHERE {where} ORDER BY Name"
    )
    classes = list(cursor.fetchall())
    if package:
        classes = [r for r in classes if r[0] and r[0].startswith(package)]
    elif exclude_system:
        classes = [r for r in classes if r[0] and not r[0].startswith("%")]
    class_names = [r[0] for r in classes]

    for name, super_str, abstract, desc in classes:
        emit({
            "type": "class",
            "name": safe_str(name),
            "super": safe_str(super_str),
            "abstract": bool(abstract),
            "description": safe_str(desc),
        })
        count += 1
        for parent in [p.strip() for p in safe_str(super_str).split(",") if p.strip()]:
            emit({"type": "inherits", "child": safe_str(name), "parent": parent})
            count += 1

    if not class_names:
        emit({"type": "done", "count": count})
        return

    in_clause = ",".join(f"'{n}'" for n in class_names)

    _QUERIES = [
        (
            "method",
            f"SELECT parent, Name, ReturnType, ClassMethod, FormalSpec, Description "
            f"FROM %Dictionary.MethodDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "method", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "return_type": safe_str(r[2]), "class_method": bool(r[3]),
                "formal_spec": safe_str(r[4]), "description": safe_str(r[5]),
            },
        ),
        (
            "property",
            f"SELECT parent, Name, Type, Collection, Description "
            f"FROM %Dictionary.PropertyDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "property", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "prop_type": safe_str(r[2]), "collection": safe_str(r[3]),
                "description": safe_str(r[4]),
            },
        ),
        (
            "parameter",
            f"SELECT parent, Name, Type, Default, Description "
            f"FROM %Dictionary.ParameterDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "parameter", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "param_type": safe_str(r[2]), "default": safe_str(r[3]),
                "description": safe_str(r[4]),
            },
        ),
        (
            "query",
            f"SELECT parent, Name, SqlName, Type, FormalSpec, Description "
            f"FROM %Dictionary.QueryDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "query", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "sql_name": safe_str(r[2]), "query_type": safe_str(r[3]),
                "formal_spec": safe_str(r[4]), "description": safe_str(r[5]),
            },
        ),
        (
            "index",
            f"SELECT parent, Name, Properties, Unique, Type "
            f"FROM %Dictionary.IndexDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "index", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "properties": safe_str(r[2]), "unique": bool(r[3]),
                "index_type": safe_str(r[4]),
            },
        ),
        (
            "xdata",
            f"SELECT parent, Name, MimeType, SchemaSpec "
            f"FROM %Dictionary.XDataDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "xdata", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "mime_type": safe_str(r[2]), "schema_spec": safe_str(r[3]),
            },
        ),
        (
            "trigger",
            f"SELECT parent, Name, Event, Foreach, Description "
            f"FROM %Dictionary.TriggerDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "trigger", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "event": safe_str(r[2]), "foreach": safe_str(r[3]),
                "description": safe_str(r[4]),
            },
        ),
        (
            "storage",
            f"SELECT parent, Name, Type "
            f"FROM %Dictionary.StorageDefinition WHERE parent IN ({in_clause}) ORDER BY parent, Name",
            lambda r: {
                "type": "storage", "class": safe_str(r[0]), "name": safe_str(r[1]),
                "storage_type": safe_str(r[2]),
            },
        ),
    ]

    for table_type, sql, row_to_record in _QUERIES:
        try:
            cursor.execute(sql)
            for row in cursor.fetchall():
                emit(row_to_record(row))
                count += 1
        except Exception as exc:
            emit_error(f"Warning: could not query {table_type}: {exc}")

    emit({"type": "done", "count": count})


def main():
    args = parse_args()
    try:
        import iris as iris_mod
        conn = iris_mod.connect(
            args.host, args.port, args.namespace, args.user, args.password
        )
    except Exception as exc:
        emit_error(f"Connection failed to {args.host}:{args.port}/{args.namespace}: {exc}")
        sys.exit(1)

    try:
        extract(conn, args.package, args.exclude_system)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
