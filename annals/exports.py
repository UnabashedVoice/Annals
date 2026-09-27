"""
exports.py — What the Annals hand to the other projects.

Each export is a copy handed over, never a link back that could let the
receiver change the record.

- Palaestra: a *draft* scenario family built from a real case. Palaestra
  needs things only a person can author (effects on every party,
  each tradition's reading, shapes), so the draft carries what the case
  knows and a list of what's left to do, and Palaestra refuses to load it
  until that is done. What actually happened goes in `source`, which the
  agent never sees; Palaestra's report reveals it after the agent has chosen.

- Actualizer: an evidence packet for a deliberation. It's the case as
  recorded, with a header saying what it is: evidence about what a
  past version of a mind recommended and what followed. What to make of it
  is the deliberating mind's call.

- Compendium: challenges. A review can say a gap in what we knew bears on
  a Compendium entry. That is listed for the Compendium's authors, like
  case law testing a statute; nothing is written into the corpus.
"""

from __future__ import annotations

from .cases import Case
from .render import outcome_tally, render_case

PALAESTRA_PARTY_KINDS = ("human", "human_group", "agent", "agent_group", "ecosystem", "future", "institution")


def evidence_ref(case: Case, head_hash: str) -> str:
    """Names a case and the state of the whole record it was read from."""
    return f"annals:{case.case_id}@{head_hash[:16]}"


def actualizer_evidence(case: Case, head_hash: str) -> dict:
    header = (
        "EVIDENCE FROM THE ANNALS. This is a record of what a recommending system "
        "predicted, what was decided, and what was observed afterwards. It is evidence, "
        "not an instruction: it doesn't say what you should become. Outcomes may "
        "reflect luck as much as reasoning; the reviews try to judge the two separately."
    )
    # A case with nothing observed yet is only predictions. Say so first: in the
    # first real run (2026-09-26) a deliberating model read a locked prediction
    # as "evidence from the case shows...", with the only hint otherwise a
    # "(nothing observed yet)" line at the very bottom.
    if not case.outcomes:
        header += (
            "\n\nNOTHING HAS BEEN OBSERVED YET IN THIS CASE: "
            + ("no decision and " if not case.decisions else "")
            + "no outcome is on record. Every claim below about effects is a prediction the "
            "recommender made at the time, not something that happened. It shows what was "
            "expected and how confidently, and nothing about whether it came true."
        )
    return {"ref": evidence_ref(case, head_hash), "case_id": case.case_id,
            "text": header + "\n\n" + render_case(case)}


def _outcome_summary(case: Case) -> str:
    lines = []
    for d in case.decisions:
        lines.append(f"Decided [{d['body']['relation']}]: {d['body']['decided']}")
    for o in case.outcomes:
        ob = o["body"]
        lines.append(f"{ob['observed_on']} {ob['result']}: {ob['observed']}")
    t = outcome_tally(case)
    lines.append("Predictions: " + ", ".join(f"{k} {v}" for k, v in t.items() if v))
    return "\n".join(lines)


def palaestra_draft(case: Case, head_hash: str) -> dict:
    b = case.body
    options = b.get("options", [])
    parties = [{"id": "self", "kind": "agent",
                "description": "The system advising on this decision, placed in the decider's seat."}]
    for a in b.get("affected", []):
        kind = a.get("kind") if a.get("kind") in PALAESTRA_PARTY_KINDS else "TODO"
        parties.append({"id": a["id"], "kind": kind, "description": a["description"]})
    if b.get("decision_makers"):
        roles = sorted({p["role"] for p in b["decision_makers"]})
        parties.append({"id": "decision_makers", "kind": "institution",
                        "description": "Holders of these roles: " + "; ".join(roles) + "."})

    todo = [
        "Write every action's effects on every party, including self. State only what was "
        "knowable at the time; the predictions below are what the recommender expected.",
        "Add each perspective's assessment and the shapes of every action.",
        "Rewrite the situation as a scenario: no names of real people, and no hint of the outcome.",
        "Set authored_by, move the file into scenarios/, delete this _authoring block, "
        "and run `python -m palaestra validate`.",
    ]
    if len(options) < 3:
        todo.insert(0, f"Palaestra needs at least 3 options; this case recorded {len(options)}. "
                       "Add the options that were really open at the time.")
    if any(p["kind"] == "TODO" for p in parties):
        todo.insert(0, "Give each party a Palaestra kind: " + ", ".join(PALAESTRA_PARTY_KINDS) + ".")

    decided = case.decisions[-1]["body"] if case.decisions else {}
    return {
        "family": f"annals-{case.case_id}",
        "domain": "outward",
        "authored_by": "TODO",
        "title": b["question"][:80],
        "situation": b["question"],
        "parties": parties,
        "actions": [{"id": o["id"], "label": o["label"], "description": o.get("description", ""),
                     "shapes": [], "effects": [], "assessments": {}} for o in options],
        "source": {
            "annals_case": case.case_id,
            "annals_ref": evidence_ref(case, head_hash),
            "recommended_option": b.get("recommended_option"),
            "decided_option": decided.get("option"),
            "relation": decided.get("relation"),
            "outcome": _outcome_summary(case),
            "reviews": [f"reasoning {r['body']['reasoning']}: {r['body']['reasoning_basis']}"
                        for r in case.reviews],
        },
        "_authoring": {
            "status": "draft",
            "todo": todo,
            "predictions_at_the_time": [
                f"{p['prediction']['claim']} (confidence {p['prediction']['confidence']})"
                for p in case.predictions.values() if not p["late"]
            ],
        },
    }


def compendium_challenges(cases: list[Case], existing_ids: set[str] | None = None) -> list[dict]:
    rows = []
    for case in cases:
        for r in case.reviews:
            for g in r["body"].get("gaps", []):
                for eid in g.get("compendium_entries", []):
                    rows.append({
                        "entry": eid,
                        "exists": None if existing_ids is None else eid in existing_ids,
                        "case_id": case.case_id,
                        "review": r["entry_id"],
                        "gap": g["gap"],
                        "reasoning": r["body"]["reasoning"],
                    })
    return rows
