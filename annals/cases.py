"""
cases.py — Folding the record into cases.

The record is a flat, append-only list of entries. A Case is a read-only
view assembled from it: everything that has been said about one decision,
in the order it was said. Nothing here writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Case:
    case_id: str
    opened: dict
    predictions: dict = field(default_factory=dict)     # id -> {"prediction", "entry", "late"}
    decisions: list = field(default_factory=list)
    outcomes: list = field(default_factory=list)
    testimonies: list = field(default_factory=list)
    reviews: list = field(default_factory=list)
    annotations: list = field(default_factory=list)

    @property
    def body(self) -> dict:
        return self.opened["body"]

    def option_ids(self) -> set:
        return {o["id"] for o in self.body.get("options", [])}

    def option_label(self, option_id) -> str:
        for o in self.body.get("options", []):
            if o["id"] == option_id:
                return o["label"]
        return str(option_id)

    def outcomes_for(self, prediction_id) -> list:
        return [e for e in self.outcomes if e["body"].get("prediction_id") == prediction_id]

    def latest_result(self, prediction_id):
        found = self.outcomes_for(prediction_id)
        return found[-1]["body"]["result"] if found else None

    def due(self, today: date) -> list[str]:
        """Predictions whose time to check has come and that have no settled observation."""
        out = []
        for pid, p in self.predictions.items():
            if date.fromisoformat(p["prediction"]["check_after"]) <= today:
                if self.latest_result(pid) in (None, "too_early"):
                    out.append(pid)
        return out


@dataclass
class RecordState:
    cases: dict = field(default_factory=dict)
    index: dict = field(default_factory=dict)            # entry_id -> entry

    def apply(self, entry: dict) -> None:
        self.index[entry["entry_id"]] = entry
        kind, body = entry["kind"], entry["body"]
        if kind == "case_opened":
            case = Case(case_id=body["case_id"], opened=entry)
            for p in body["predictions"]:
                case.predictions[p["id"]] = {"prediction": p, "entry": entry, "late": None}
            self.cases[case.case_id] = case
            return
        case = self.cases.get(body.get("case_id"))
        if case is None:
            return
        if kind == "prediction_added":
            p = body["prediction"]
            case.predictions[p["id"]] = {"prediction": p, "entry": entry, "late": body["known_when_made"]}
        elif kind == "decision_recorded":
            case.decisions.append(entry)
        elif kind == "outcome_observed":
            case.outcomes.append(entry)
        elif kind == "testimony":
            case.testimonies.append(entry)
        elif kind == "review":
            case.reviews.append(entry)
        elif kind == "annotation":
            case.annotations.append(entry)
