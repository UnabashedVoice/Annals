"""
entries.py — The kinds of entry the Annals accept, and what each must say.

A case is told over time, one entry per event, never by editing:

    case_opened         the recommendation and its predictions, locked before any outcome
    prediction_added    a later prediction, stamped with what was already known when it was made
    decision_recorded   what was actually decided, and by whom (named, with their position)
    outcome_observed    what happened, against one prediction, or something nobody predicted
    testimony           an account from someone affected (pseudonymous by default)
    review              a look-back: was the reasoning sound given what was knowable then,
                        and what did we fail to know? Judged apart from the outcome.
    annotation          a note on any earlier entry: correction, context, or a later
                        generation's reply. The entry it annotates stays as it was.

What happened on the road not taken is never recorded, because it was never
observed. The record has no field for it.
"""

from __future__ import annotations

import re
from datetime import date

from .identity import check_author, check_person, check_system, new_pseudonym

KINDS = (
    "case_opened", "prediction_added", "decision_recorded", "outcome_observed",
    "testimony", "review", "annotation",
)
RELATIONS = ("followed", "partially_followed", "departed", "no_decision")
RESULTS = ("held", "failed", "mixed", "too_early", "unresolvable", "unanticipated")
REASONING = ("sound", "flawed", "mixed", "cannot_judge")
ANNOTATION_KINDS = ("note", "correction", "context", "descendant")


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _iso_date(v, where: str, errs: list[str]) -> None:
    try:
        date.fromisoformat(v)
    except (TypeError, ValueError):
        errs.append(f"{where}: must be an ISO date (YYYY-MM-DD), got {v!r}")


def _only(body: dict, allowed: set[str], where: str, errs: list[str]) -> None:
    extra = set(body) - allowed
    if extra:
        errs.append(f"{where}: unknown fields {sorted(extra)}")


def _check_prediction(p, where: str, errs: list[str]) -> None:
    if not isinstance(p, dict):
        errs.append(f"{where}: must be an object")
        return
    _only(p, {"id", "claim", "confidence", "wrong_if", "check_after", "derived_from", "confidence_basis"}, where, errs)
    for k in ("id", "claim", "wrong_if"):
        if not _text(p.get(k)):
            errs.append(f"{where}: {k!r} is required" + (
                " (what result would show this prediction was wrong?)" if k == "wrong_if" else ""))
    c = p.get("confidence")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0.0 <= c <= 1.0:
        errs.append(f"{where}: confidence must be a number in [0, 1]")
    _iso_date(p.get("check_after"), f"{where}.check_after", errs)


def _people(items, where: str, errs: list[str], *, require_authority: bool) -> list:
    if not isinstance(items, list):
        errs.append(f"{where}: must be a list")
        return items
    out = []
    for i, p in enumerate(items):
        norm, e = check_person(p, f"{where}[{i}]", require_authority=require_authority)
        errs.extend(e)
        out.append(norm)
    return out


def _affected(items, where: str, errs: list[str]) -> list:
    """Affected parties are described, not named; a pseudonym is assigned per party."""
    if not isinstance(items, list):
        errs.append(f"{where}: must be a list")
        return items
    out = []
    for i, a in enumerate(items):
        w = f"{where}[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{w}: must be an object")
            continue
        _only(a, {"id", "description", "kind"}, w, errs)
        if not _text(a.get("description")):
            errs.append(f"{w}: 'description' is required")
        out.append({**a, "id": a.get("id") or new_pseudonym()})
    return out


def validate(kind: str, body: dict, author, state) -> tuple[dict, dict, list[str]]:
    """
    Check an entry against the record as it stands. Returns the body and
    author normalized (pseudonyms assigned), plus any errors. `state` is a
    cases.RecordState.
    """
    errs: list[str] = []
    if kind not in KINDS:
        return body, author, [f"unknown entry kind {kind!r}; one of {KINDS}"]
    if not isinstance(body, dict):
        return body, author, ["the entry body must be an object"]
    author, e = check_author(author, "author")
    errs.extend(e)
    body = dict(body)
    where = kind

    case = None
    if kind != "case_opened" and kind != "annotation":
        case = state.cases.get(body.get("case_id"))
        if case is None:
            errs.append(f"{where}: no such case {body.get('case_id')!r}")
            return body, author, errs

    if kind == "case_opened":
        _only(body, {"question", "recommender", "recommendation", "recommended_option", "options",
                     "predictions", "decision_makers", "affected", "source", "escalation", "brief"},
              where, errs)
        esc = body.get("escalation")
        if esc is not None:
            if not isinstance(esc, dict) or not isinstance(esc.get("triggers"), list) or not esc["triggers"]:
                errs.append(f"{where}.escalation: must say what triggered it (a non-empty 'triggers' list)")
        brief = body.get("brief")
        if brief is not None:
            if not isinstance(brief, dict):
                errs.append(f"{where}.brief: must be an object")
            elif brief.get("why_human_judgment") is not None and not brief.get("decision_questions"):
                errs.append(f"{where}.brief: a brief must list the questions the decision-makers must answer")
        for k in ("question", "recommendation"):
            if not _text(body.get(k)):
                errs.append(f"{where}: {k!r} is required")
        errs.extend(check_system(body.get("recommender"), f"{where}.recommender"))
        preds = body.get("predictions")
        if not isinstance(preds, list) or not preds:
            errs.append(f"{where}: at least one prediction is required: a recommendation that "
                        "predicts nothing can't be checked against what happens")
        else:
            for i, p in enumerate(preds):
                _check_prediction(p, f"{where}.predictions[{i}]", errs)
            ids = [p.get("id") for p in preds if isinstance(p, dict)]
            if len(set(ids)) != len(ids):
                errs.append(f"{where}: duplicate prediction ids")
        options = body.get("options", [])
        if not isinstance(options, list):
            errs.append(f"{where}.options: must be a list")
            options = []
        for i, o in enumerate(options):
            if not isinstance(o, dict) or not _text(o.get("id")) or not _text(o.get("label")):
                errs.append(f"{where}.options[{i}]: needs an id and a label")
        option_ids = {o.get("id") for o in options if isinstance(o, dict)}
        rec = body.get("recommended_option")
        if rec is not None and rec not in option_ids:
            errs.append(f"{where}: recommended_option {rec!r} is not among the options")
        body["decision_makers"] = _people(body.get("decision_makers", []), f"{where}.decision_makers",
                                          errs, require_authority=True)
        body["affected"] = _affected(body.get("affected", []), f"{where}.affected", errs)

    elif kind == "prediction_added":
        _only(body, {"case_id", "prediction"}, where, errs)
        _check_prediction(body.get("prediction"), f"{where}.prediction", errs)
        pid = (body.get("prediction") or {}).get("id") if isinstance(body.get("prediction"), dict) else None
        if pid in case.predictions:
            errs.append(f"{where}: prediction id {pid!r} already exists in this case")
        # Stamped by the record, not the writer: a prediction made after
        # the decision or after outcomes began to come in is still worth
        # having, but it must never read as if it came first.
        body["known_when_made"] = {
            "decisions_recorded": len(case.decisions),
            "outcomes_observed": len(case.outcomes),
        }

    elif kind == "decision_recorded":
        _only(body, {"case_id", "decided", "option", "relation", "deciders"}, where, errs)
        if not _text(body.get("decided")):
            errs.append(f"{where}: 'decided' is required (what was actually decided)")
        if body.get("relation") not in RELATIONS:
            errs.append(f"{where}: relation must be one of {RELATIONS} (relative to the recommendation)")
        opt = body.get("option")
        if opt is not None and opt not in case.option_ids():
            errs.append(f"{where}: option {opt!r} is not among the case's options")
        deciders = body.get("deciders")
        if not isinstance(deciders, list) or not deciders:
            errs.append(f"{where}: at least one decider is required: someone had the authority")
        else:
            body["deciders"] = _people(deciders, f"{where}.deciders", errs, require_authority=True)
            for i, d in enumerate(body["deciders"]):
                if isinstance(d, dict) and "position" not in d:
                    errs.append(f"{where}.deciders[{i}]: 'position' is required ({', '.join(('decided', 'for', 'against', 'abstained'))})")

    elif kind == "outcome_observed":
        _only(body, {"case_id", "prediction_id", "result", "observed", "evidence", "observed_on"}, where, errs)
        if body.get("result") not in RESULTS:
            errs.append(f"{where}: result must be one of {RESULTS}")
        pid = body.get("prediction_id")
        if body.get("result") == "unanticipated":
            if pid is not None:
                errs.append(f"{where}: an unanticipated outcome belongs to no prediction; leave prediction_id null")
        elif pid not in case.predictions:
            errs.append(f"{where}: no prediction {pid!r} in this case (use result 'unanticipated' "
                        "for something nobody predicted)")
        if not case.decisions:
            errs.append(f"{where}: record the decision first: an outcome follows from what was decided, "
                        "not from what was recommended")
        if not _text(body.get("observed")):
            errs.append(f"{where}: 'observed' is required")
        if not isinstance(body.get("evidence", []), list):
            errs.append(f"{where}: evidence must be a list")
        _iso_date(body.get("observed_on"), f"{where}.observed_on", errs)

    elif kind == "testimony":
        _only(body, {"case_id", "teller", "account", "about_entry"}, where, errs)
        teller, e = check_person(body.get("teller"), f"{where}.teller")
        errs.extend(e)
        body["teller"] = teller
        if not _text(body.get("account")):
            errs.append(f"{where}: 'account' is required")
        about = body.get("about_entry")
        if about is not None and about not in state.index:
            errs.append(f"{where}: about_entry {about!r} is not in the record")

    elif kind == "review":
        _only(body, {"case_id", "reasoning", "reasoning_basis", "knowable_then", "gaps"}, where, errs)
        if body.get("reasoning") not in REASONING:
            errs.append(f"{where}: reasoning must be one of {REASONING}")
        if not _text(body.get("reasoning_basis")):
            errs.append(f"{where}: 'reasoning_basis' is required: why, judged by what was knowable then")
        if not case.decisions:
            errs.append(f"{where}: a review looks back on a decision; none is recorded yet")
        if not (isinstance(author, dict) and "system" not in author and author.get("name")):
            errs.append(f"{where}: a review is written by a named reviewer: a judgment of someone's "
                        "reasoning carries the reviewer's name")
        gaps = body.get("gaps", [])
        if not isinstance(gaps, list):
            errs.append(f"{where}.gaps: must be a list")
        else:
            for i, g in enumerate(gaps):
                w = f"{where}.gaps[{i}]"
                if not isinstance(g, dict) or not _text(g.get("gap")):
                    errs.append(f"{w}: needs 'gap' (what we failed to know)")
                    continue
                _only(g, {"gap", "compendium_entries", "palaestra"}, w, errs)
                ce = g.get("compendium_entries", [])
                if not isinstance(ce, list) or not all(re.fullmatch(r"[a-z0-9-]+", x or "") for x in ce):
                    errs.append(f"{w}: compendium_entries must be a list of entry ids")
                if not isinstance(g.get("palaestra", False), bool):
                    errs.append(f"{w}: palaestra must be true or false (worth a scenario?)")

    elif kind == "annotation":
        _only(body, {"target", "kind", "text"}, where, errs)
        target = state.index.get(body.get("target"))
        if target is None:
            errs.append(f"{where}: target {body.get('target')!r} is not in the record")
        else:
            body["case_id"] = target["body"].get("case_id")
        if body.get("kind") not in ANNOTATION_KINDS:
            errs.append(f"{where}: kind must be one of {ANNOTATION_KINDS}")
        if not _text(body.get("text")):
            errs.append(f"{where}: 'text' is required")

    return body, author, errs
