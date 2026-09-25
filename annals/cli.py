"""
cli.py — `python -m annals ...`

Every write goes through `add` (or `intake-arbitrator`, which builds a
case_opened entry from an Arbitrator run). There is no edit or delete
command because there is no edit or delete.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .entries import KINDS
from .exports import actualizer_evidence, compendium_challenges, palaestra_draft
from .intake import case_from_arbitrator
from .provenance import compendium_entry_ids, git_version
from .record import Annals, RecordError, RecordIntegrityError
from .render import render_case

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECORD = ROOT / "record" / "annals.jsonl"
SIBLING_COMPENDIUM = ROOT.parent / "Compendium"


def _record(args) -> Annals:
    return Annals(args.record or os.environ.get("ANNALS_RECORD") or DEFAULT_RECORD)


def _read_json(path: str):
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _emit(obj, out: str | None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"written to {out}")
    else:
        print(text)


def _append(annals: Annals, kind: str, body: dict, author: dict) -> int:
    try:
        e = annals.append(kind, body, author)
    except (RecordError, RecordIntegrityError) as ex:
        print(ex, file=sys.stderr)
        return 1
    extra = f" case {e['body']['case_id']}" if kind == "case_opened" else ""
    print(f"recorded {e['kind']} {e['entry_id']}{extra} (seq {e['seq']}, hash {e['hash'][:16]})")
    return 0


def cmd_add(args) -> int:
    doc = _read_json(args.file)
    if set(doc) != {"author", "body"}:
        print("the file must hold exactly {\"author\": ..., \"body\": ...}", file=sys.stderr)
        return 2
    return _append(_record(args), args.kind, doc["body"], doc["author"])


def cmd_intake_arbitrator(args) -> int:
    result = _read_json(args.result)
    people = _read_json(args.people) if args.people else {}
    try:
        body = case_from_arbitrator(
            result, arbitrator_version=args.arbitrator_version,
            code_version=git_version(args.arbitrator_repo) if args.arbitrator_repo else "unknown",
            question=args.question, decision_makers=people.get("decision_makers"),
            affected=people.get("affected"))
    except ValueError as ex:
        print(ex, file=sys.stderr)
        return 1
    return _append(_record(args), "case_opened", body, body["recommender"])


def cmd_list(args) -> int:
    today = date.today()
    for c in _record(args).cases():
        due = len(c.due(today))
        print(f"{c.case_id}  decisions {len(c.decisions)}  outcomes {len(c.outcomes)}  "
              f"reviews {len(c.reviews)}" + (f"  DUE {due}" if due else ""))
    return 0


def cmd_show(args) -> int:
    try:
        print(render_case(_record(args).case(args.case), today=date.today()))
    except KeyError as ex:
        print(ex.args[0], file=sys.stderr)
        return 1
    return 0


def cmd_due(args) -> int:
    today = date.fromisoformat(args.today) if args.today else date.today()
    any_due = False
    for c in _record(args).cases():
        for pid in c.due(today):
            any_due = True
            p = c.predictions[pid]["prediction"]
            print(f"{c.case_id} [{pid}] check after {p['check_after']}: {p['claim']}")
    if not any_due:
        print("nothing is due")
    return 0


def cmd_verify(args) -> int:
    annals = _record(args)
    problems = annals.verify()
    if problems:
        print("THE RECORD DOES NOT VERIFY:\n  " + "\n  ".join(problems))
        return 1
    if args.anchor is not None:
        if len(args.anchor) < 12:
            print("give at least the first 12 characters of the published hash")
            return 2
        hit = next((e for e in annals.entries() if e["hash"].startswith(args.anchor.lower())), None)
        if hit is None:
            print(f"record intact, but it does not contain the published head {args.anchor}: "
                  "this is not the record that was anchored")
            return 1
        print(f"record intact, and contains the published head {args.anchor} (entry {hit['seq']})")
        return 0
    print("record intact")
    return 0


def cmd_head(args) -> int:
    h = _record(args).head()
    print(f"annals head: {h['entries']} entries, {h['hash']} ({h['recorded_at']})")
    return 0


def cmd_export(args) -> int:
    annals = _record(args)
    try:
        case = annals.case(args.case)
    except KeyError as ex:
        print(ex.args[0], file=sys.stderr)
        return 1
    head = annals.head()["hash"]
    if args.target == "palaestra":
        _emit(palaestra_draft(case, head), args.out)
    else:
        _emit(actualizer_evidence(case, head), args.out)
    return 0


def cmd_challenges(args) -> int:
    root = Path(args.compendium) if args.compendium else SIBLING_COMPENDIUM
    ids = compendium_entry_ids(root) if (root / "entries").exists() else None
    rows = compendium_challenges(_record(args).cases(), ids)
    if not rows:
        print("no review has cited a Compendium entry")
    for r in rows:
        status = {True: "", False: " (entry not written yet)", None: ""}[r["exists"]]
        print(f"{r['entry']}{status}\n  {r['case_id']} (review {r['review']}, reasoning {r['reasoning']}): {r['gap']}")
    return 0


def main(argv=None) -> int:
    # Entries carry free text written by whoever recorded them (a
    # recommendation, testimony, a reviewer's reasoning) and can contain
    # arbitrary Unicode; `show`/`export` print that text back. A narrower
    # default console codepage would raise on it instead of printing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    ap = argparse.ArgumentParser(prog="annals", description="The append-only record of recommendations and what followed.")
    ap.add_argument("--record", help=f"record file (default $ANNALS_RECORD or {DEFAULT_RECORD})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="append one entry from a JSON file {author, body}")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("file", help="JSON file, or - for stdin")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("intake-arbitrator", help="open a case from an Arbitrator result (arbitrator run --json)")
    p.add_argument("result")
    p.add_argument("--arbitrator-version", default="0.1.0")
    p.add_argument("--arbitrator-repo", help="Arbitrator checkout, for the commit hash")
    p.add_argument("--question", help="the decision under consideration, if not the proposal text")
    p.add_argument("--people", help="JSON file {decision_makers: [...], affected: [...]}")
    p.set_defaults(fn=cmd_intake_arbitrator)

    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("show")
    p.add_argument("case")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("due", help="predictions whose time to check has come")
    p.add_argument("--today", help="YYYY-MM-DD (default: today)")
    p.set_defaults(fn=cmd_due)
    p = sub.add_parser("verify")
    p.add_argument("--anchor", help="a head hash published earlier; checks this record still contains it")
    p.set_defaults(fn=cmd_verify)
    sub.add_parser("head", help="the line to publish somewhere outside your control").set_defaults(fn=cmd_head)

    p = sub.add_parser("export")
    p.add_argument("target", choices=("palaestra", "actualizer"))
    p.add_argument("case")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("challenges", help="Compendium entries that reviews say a gap bears on")
    p.add_argument("--compendium", help=f"Compendium root (default {SIBLING_COMPENDIUM})")
    p.set_defaults(fn=cmd_challenges)

    args = ap.parse_args(argv)
    return args.fn(args)
