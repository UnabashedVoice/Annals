"""
record.py — The Annals record: append-only, hash-chained, never edited.

One JSON object per line. Each entry carries the hash of the one before
it, so changing, removing, or reordering any past entry breaks every hash
after it, and `verify()` says where. Corrections are new entries
(annotations) that point at the old one; the old one stays as written.

What the chain proves is order and integrity *within* the file. It can't
prove the file wasn't written all at once, later. For that, publish the
head hash somewhere outside your control from time to time (a git commit
in a public repo is enough); `head()` gives you the line to publish.

`recorded_at` is always the clock at the moment of writing and can't be
supplied by the writer. Dates that belong to the world (when something
was observed, when a prediction can be checked) are separate fields.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from .cases import Case, RecordState
from .entries import validate

GENESIS = "0" * 64


class RecordError(Exception):
    """An entry was refused. The record is unchanged."""


class RecordIntegrityError(Exception):
    """The record on disk does not verify. Nothing will be appended to it."""


def _canonical(entry: dict) -> str:
    return json.dumps({k: v for k, v in entry.items() if k != "hash"},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def entry_hash(entry: dict) -> str:
    return hashlib.sha256(_canonical(entry).encode("utf-8")).hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].rstrip("-") or "case"


class Annals:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        self.state = RecordState()
        self.problems: list[str] = []
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        self._entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        self.problems.append(f"line {n}: not valid JSON (a partial write?)")
        self.problems += self._check_chain()
        for e in self._entries:
            self.state.apply(e)

    # -- integrity ---------------------------------------------------------

    def _check_chain(self) -> list[str]:
        problems, prev = [], GENESIS
        for i, e in enumerate(self._entries):
            where = f"entry {i} ({e.get('entry_id', '?')})"
            if e.get("seq") != i:
                problems.append(f"{where}: sequence {e.get('seq')} where {i} was expected")
            if e.get("prev_hash") != prev:
                problems.append(f"{where}: does not follow the entry before it")
            if entry_hash(e) != e.get("hash"):
                problems.append(f"{where}: contents do not match its hash (edited after writing)")
            prev = e.get("hash")
        return problems

    def verify(self) -> list[str]:
        """Re-read the file from disk and check the whole chain. Empty list means intact."""
        return Annals(self.path).problems

    def head(self) -> dict:
        last = self._entries[-1] if self._entries else None
        return {"entries": len(self._entries), "hash": last["hash"] if last else GENESIS,
                "recorded_at": last["recorded_at"] if last else None}

    # -- writing -----------------------------------------------------------

    def append(self, kind: str, body: dict, author: dict) -> dict:
        """Validate against the record as it stands, then append. Raises RecordError if refused."""
        if self.problems:
            raise RecordIntegrityError(
                "the record does not verify; nothing will be added until that is resolved:\n  "
                + "\n  ".join(self.problems))
        with self._lock:
            # Round-trip through JSON: the entry must be exactly what will
            # be on disk, and must share nothing the caller could mutate.
            body, author = json.loads(json.dumps(body)), json.loads(json.dumps(author))
            body, author, errs = validate(kind, body, author, self.state)
            if errs:
                raise RecordError("entry refused:\n  " + "\n  ".join(errs))
            now = datetime.now(timezone.utc)
            if kind == "case_opened":
                body = {"case_id": f"{now:%Y-%m-%d}-{_slug(body['question'])}-{secrets.token_hex(2)}", **body}
            entry = {
                "seq": len(self._entries),
                "entry_id": "e-" + secrets.token_hex(6),
                "kind": kind,
                "recorded_at": now.isoformat(),
                "author": author,
                "body": body,
                "prev_hash": self._entries[-1]["hash"] if self._entries else GENESIS,
            }
            entry["hash"] = entry_hash(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._entries.append(entry)
            self.state.apply(entry)
            return entry

    # -- reading -----------------------------------------------------------

    def entries(self) -> list[dict]:
        return list(self._entries)

    def case(self, case_id: str) -> Case:
        if case_id not in self.state.cases:
            raise KeyError(f"no such case: {case_id}")
        return self.state.cases[case_id]

    def cases(self) -> list[Case]:
        return list(self.state.cases.values())
