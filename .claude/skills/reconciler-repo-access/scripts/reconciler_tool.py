#!/usr/bin/env python3
"""reconciler_tool.py — mechanical helpers for reconciler-repo records.

The reconciler repo stores JSON *arrays* of records keyed by an ``id`` field
under ``data/`` (operational state):
  - data/to-be-models.json                       -> array of ToBeModel
  - data/reconciliation-tasks/<toBeModelId>.json  -> array of ReconciliationTask

This tool handles the error-prone plumbing (schema validation, keyed upsert,
id allocation) so the skill can focus on judgment. It never talks to git or the
network; run it against files already checked out in the repo.

Subcommands
-----------
  validate     --schema S --data D
        Validate every element of the JSON array in D against JSON Schema S
        (Draft 2020-12). Exit non-zero and print the first errors on failure.

  check-schema --schema S [--sample G ...]
        Assert S is itself a well-formed JSON Schema, then (optionally) validate
        each --sample file/glob against it. Use before committing a schema edit.

  upsert       --file F --id ID (--patch P | --patch-json JSON)
               [--create] [--schema S]
        Deep-merge the patch into the record whose id == ID inside array file F.
        With --create, insert the patch as a new record when ID is absent.
        With --schema, validate the *changed* record before writing.
        Writes back with stable 2-space indentation + trailing newline.

  get          --file F --id ID
        Print the record whose id == ID (empty string if none).

  next-id      --file F [--prefix rct] [--date YYYYMMDD]
        Print the next free sequential id of the form <prefix>_<date>-<NNNN>,
        scanning existing ids in F for the same prefix+date.

Merge semantics: dicts merge recursively; lists and scalars in the patch replace
the target wholesale (so you can set an entire ``steps`` array in one call).
Setting a value to null deletes that key (lets you clear a field intentionally).
"""
import argparse
import datetime as _dt
import glob as _glob
import json
import re
import sys


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _validator(schema):
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _deep_merge(target, patch):
    """Recursively merge patch into target. null in patch deletes the key."""
    if not isinstance(target, dict) or not isinstance(patch, dict):
        return patch
    out = dict(target)
    for key, val in patch.items():
        if val is None:
            out.pop(key, None)
        elif isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def cmd_validate(args):
    schema = _load(args.schema)
    data = _load(args.data)
    validator = _validator(schema)
    records = data if isinstance(data, list) else [data]
    errors = []
    for idx, record in enumerate(records):
        rid = record.get("id", f"index {idx}") if isinstance(record, dict) else f"index {idx}"
        for err in validator.iter_errors(record):
            loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
            errors.append(f"  [{rid}] {loc}: {err.message}")
    if errors:
        print(f"INVALID: {len(errors)} error(s) in {args.data}", file=sys.stderr)
        print("\n".join(errors[:40]), file=sys.stderr)
        return 1
    print(f"OK: {len(records)} record(s) in {args.data} conform to {args.schema}")
    return 0


def cmd_check_schema(args):
    schema = _load(args.schema)
    try:
        _validator(schema)
    except Exception as exc:  # noqa: BLE001 - surface any schema defect
        print(f"INVALID SCHEMA {args.schema}: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {args.schema} is a valid JSON Schema")
    rc = 0
    for pattern in args.sample or []:
        for path in sorted(_glob.glob(pattern)):
            sub = argparse.Namespace(schema=args.schema, data=path)
            rc = cmd_validate(sub) or rc
    return rc


def cmd_upsert(args):
    data = _load(args.file)
    if not isinstance(data, list):
        print(f"ERROR: {args.file} is not a JSON array", file=sys.stderr)
        return 2
    if args.patch_json is not None:
        patch = json.loads(args.patch_json)
    else:
        patch = _load(args.patch)

    idx = next((i for i, r in enumerate(data) if isinstance(r, dict) and r.get("id") == args.id), None)
    if idx is None:
        if not args.create:
            print(f"ERROR: id {args.id} not found in {args.file} (pass --create to insert)", file=sys.stderr)
            return 2
        record = dict(patch)
        record.setdefault("id", args.id)
        data.append(record)
        action = "created"
    else:
        record = _deep_merge(data[idx], patch)
        data[idx] = record
        action = "updated"

    if args.schema:
        validator = _validator(_load(args.schema))
        errs = sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
        if errs:
            print(f"REFUSED: patched record {args.id} would violate {args.schema}:", file=sys.stderr)
            for err in errs[:20]:
                loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
                print(f"  {loc}: {err.message}", file=sys.stderr)
            return 1

    _dump(args.file, data)
    print(f"{action} {args.id} in {args.file}")
    return 0


def cmd_get(args):
    data = _load(args.file)
    for record in data if isinstance(data, list) else []:
        if isinstance(record, dict) and record.get("id") == args.id:
            print(json.dumps(record, ensure_ascii=False, indent=2))
            return 0
    return 0


def cmd_next_id(args):
    date = args.date or _dt.date.today().strftime("%Y%m%d")
    prefix = f"{args.prefix}_{date}-"
    try:
        data = _load(args.file)
    except FileNotFoundError:
        data = []
    seqs = []
    pat = re.compile(re.escape(prefix) + r"(\d+)$")
    for record in data if isinstance(data, list) else []:
        if isinstance(record, dict):
            m = pat.match(str(record.get("id", "")))
            if m:
                seqs.append(int(m.group(1)))
    nxt = (max(seqs) + 1) if seqs else 1
    print(f"{prefix}{nxt:04d}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="reconciler repo record helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate")
    p.add_argument("--schema", required=True)
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("check-schema")
    p.add_argument("--schema", required=True)
    p.add_argument("--sample", action="append")
    p.set_defaults(func=cmd_check_schema)

    p = sub.add_parser("upsert")
    p.add_argument("--file", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--patch")
    p.add_argument("--patch-json")
    p.add_argument("--create", action="store_true")
    p.add_argument("--schema")
    p.set_defaults(func=cmd_upsert)

    p = sub.add_parser("get")
    p.add_argument("--file", required=True)
    p.add_argument("--id", required=True)
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("next-id")
    p.add_argument("--file", required=True)
    p.add_argument("--prefix", default="rct")
    p.add_argument("--date")
    p.set_defaults(func=cmd_next_id)

    args = parser.parse_args(argv)
    if args.cmd == "upsert" and args.patch is None and args.patch_json is None:
        parser.error("upsert requires --patch or --patch-json")
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Downstream (e.g. `| head`) closed the pipe; exit quietly.
        try:
            sys.stdout.close()
        finally:
            sys.exit(0)
