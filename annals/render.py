"""
render.py — Plain-text views of the record.

A case reads as three columns told in order: what was recommended, what
was decided, what happened. The look-back comes after, and puts the
judgment of the reasoning beside the outcome without merging them: sound
reasoning can meet a bad outcome, and luck can rescue bad reasoning.
"""

from __future__ import annotations

from datetime import date

from .cases import Case
from .identity import display


def _day(ts: str) -> str:
    return ts[:10]


def outcome_tally(case: Case) -> dict:
    tally = {"held": 0, "failed": 0, "mixed": 0, "open": 0, "unresolvable": 0}
    for pid in case.predictions:
        r = case.latest_result(pid)
        tally["open" if r in (None, "too_early") else r] += 1
    tally["unanticipated"] = sum(1 for e in case.outcomes if e["body"]["result"] == "unanticipated")
    return tally


def resulting_note(reasoning: str, tally: dict) -> str | None:
    """The two cells of the reasoning-by-outcome table that are easiest to misread."""
    missed = tally["failed"] + tally["mixed"] + tally["unanticipated"]
    if reasoning == "sound" and missed:
        return ("Sound reasoning, outcome missed: read this as a lesson about what was knowable, "
                "not a verdict on the reasoning.")
    if reasoning == "flawed" and not missed and tally["held"]:
        return ("Flawed reasoning, predictions held anyway: don't read the outcome as vindication.")
    return None


def render_case(case: Case, today: date | None = None) -> str:
    b = case.body
    out = [f"CASE {case.case_id}", f"Question: {b['question']}",
           f"Opened {_day(case.opened['recorded_at'])} by {display(b['recommender'])}"]
    if b.get("decision_makers"):
        out.append("Addressed to: " + "; ".join(display(p) for p in b["decision_makers"]))
    for a in b.get("affected", []):
        out.append(f"Affected: {a['id']}: {a['description']}")

    out += ["", f"RECOMMENDED (locked {_day(case.opened['recorded_at'])})", f"  {b['recommendation']}"]
    if b.get("recommended_option"):
        out.append(f"  Option: {case.option_label(b['recommended_option'])}")

    esc = b.get("escalation")
    if esc:
        out += ["", "ESCALATED FOR HUMAN REVIEW"]
        for t in esc.get("triggers", []):
            out.append(f"  trigger [{t.get('source')}]: {t.get('detail')}")
    br = b.get("brief")
    if br:
        out += ["", f"DECISION BRIEF (by {br.get('brief_by')})"]
        if br.get("brief_error"):
            out.append(f"  Not produced: {br['brief_error']}")
        if br.get("why_human_judgment"):
            out.append(f"  Judgment calls: {br['why_human_judgment']}")
            for q in br.get("decision_questions") or []:
                out.append(f"  To decide: {q}")
            aside = {a.get("option"): a.get("because") for a in br.get("set_aside") or [] if isinstance(a, dict)}
            for o in b.get("options", []):
                out.append(f"  Option [{o['id']}] {o['label']}: {o.get('description', '')}")
                if o["id"] in aside:
                    out.append(f"      set aside because: {aside[o['id']]}")
            lean = br.get("provisional_lean") or {}
            if lean:
                out.append(f"  Provisional lean: {lean.get('option')} (confidence {lean.get('confidence')})")
                if lean.get("reasoning"):
                    out.append(f"      reasoning: {lean['reasoning']}")
                out.append(f"      would change if: {lean.get('would_change_if')}")
            review = br.get("review") or {}
            if review:
                out.append(f"  Brief-writer's view: {'needs' if review.get('needed') else 'does not need'} "
                           f"human sign-off. {review.get('why', '')}")

    out += ["", "PREDICTIONS"]
    for pid, p in case.predictions.items():
        pr = p["prediction"]
        line = f"  [{pid}] {pr['claim']} (confidence {pr['confidence']}; check after {pr['check_after']})"
        out.append(line)
        out.append(f"      wrong if: {pr['wrong_if']}")
        if pr.get("confidence_basis"):
            out.append(f"      confidence basis: {pr['confidence_basis']}")
        if p["late"]:
            k = p["late"]
            out.append(f"      added {_day(p['entry']['recorded_at'])}, after {k['decisions_recorded']} "
                       f"decision(s) and {k['outcomes_observed']} outcome(s) were on record")
        for o in case.outcomes_for(pid):
            ob = o["body"]
            out.append(f"      -> {ob['result'].upper()} (observed {ob['observed_on']}): {ob['observed']}")

    out += ["", "DECIDED"]
    if not case.decisions:
        out.append("  (nothing recorded yet)")
    for d in case.decisions:
        db = d["body"]
        out.append(f"  {_day(d['recorded_at'])} [{db['relation']}] {db['decided']}")
        if db.get("option"):
            out.append(f"    Option: {case.option_label(db['option'])}")
        for p in db["deciders"]:
            out.append(f"    {display(p)}: {p['position']}")
    taken = {d["body"].get("option") for d in case.decisions}
    rec = b.get("recommended_option")
    if case.decisions and (case.decisions[-1]["body"]["relation"] != "followed" or (rec and rec not in taken)):
        out.append("  The road not taken is unobserved: what the recommendation would have done "
                   "is not in this record, and nothing here should be read as if it were.")

    out += ["", "HAPPENED"]
    if not case.outcomes:
        out.append("  (nothing observed yet)")
    for o in case.outcomes:
        ob = o["body"]
        about = f"[{ob['prediction_id']}]" if ob.get("prediction_id") else "[not predicted]"
        out.append(f"  {ob['observed_on']} {about} {ob['result']}: {ob['observed']}")
        for ev in ob.get("evidence", []):
            out.append(f"      evidence: {ev}")
    if today:
        due = case.due(today)
        if due:
            out.append(f"  Due for a look: {', '.join(due)}")

    tally = outcome_tally(case)
    out += ["", "LOOK-BACK",
            "  Outcomes: " + ", ".join(f"{k} {v}" for k, v in tally.items() if v)]
    for r in case.reviews:
        rb = r["body"]
        out.append(f"  Review by {display(r['author'])}, {_day(r['recorded_at'])}: reasoning {rb['reasoning'].upper()}")
        out.append(f"    {rb['reasoning_basis']}")
        if rb.get("knowable_then"):
            out.append(f"    Knowable then: {rb['knowable_then']}")
        for g in rb.get("gaps", []):
            tags = []
            if g.get("compendium_entries"):
                tags.append("Compendium: " + ", ".join(g["compendium_entries"]))
            if g.get("palaestra"):
                tags.append("worth a Palaestra scenario")
            out.append(f"    Failed to know: {g['gap']}" + (f" ({'; '.join(tags)})" if tags else ""))
        note = resulting_note(rb["reasoning"], tally)
        if note:
            out.append(f"    Note: {note}")

    if case.testimonies:
        out += ["", "TESTIMONY"]
        for t in case.testimonies:
            out.append(f"  {display(t['body']['teller'])}, {_day(t['recorded_at'])}: {t['body']['account']}")

    if case.annotations:
        out += ["", "ANNOTATIONS (the entries they annotate stand as written)"]
        for a in case.annotations:
            ab = a["body"]
            out.append(f"  on {ab['target']} [{ab['kind']}] {display(a['author'])}, "
                       f"{_day(a['recorded_at'])}: {ab['text']}")
    return "\n".join(out)
