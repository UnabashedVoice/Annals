"""
intake.py — Opening a case from an Arbitrator run.

Arbitrator produces a consequence map, not a list of predictions. Each
finding in it is a claim about the future, though: this group, this effect,
in this timeframe, with this certainty. Intake turns each finding into a
prediction and locks it, so that when the timeframe comes round there is
something specific to check.

A run the Ethics Core stopped before any channel ran has no consequence
map, but it is still a recommendation (don't do this), so it is recorded
too: one prediction that the action, if carried out, does more harm than
good (or crosses the named hard constraints). See _case_from_block.

Two things are derived rather than stated by Arbitrator, and each
prediction says so, so nobody mistakes the derivation for Arbitrator's own
words:

- confidence, mapped from the finding's certainty label
  (findings whose certainty is "unknown" are left out: no number can be
  honestly given to them, and they're listed in the recommendation instead);
- check_after, the earliest date the finding's timeframe allows it to be
  judged.

The recommender identity is built from the run: models from each channel's
output, Arbitrator's version and commit, and the Compendium consultation if
the run made one (`run --compendium`): which build of the Compendium, and
which entries of it the model chose. A run that didn't consult it says
"not consulted". Arbitrator does not train in Palaestra, and the identity
says that too.
"""

from __future__ import annotations

from datetime import date, timedelta

CONFIDENCE = {"high": 0.85, "moderate": 0.6, "low": 0.3}
# Earliest point at which a finding in each timeframe can be judged.
CHECK_AFTER_DAYS = {
    "immediate": 90, "short_term": 2 * 365, "medium_term": 10 * 365,
    "long_term": 50 * 365, "generational": 50 * 365,
}


def _findings(cmap: dict) -> list[dict]:
    """Every finding once, each with an id unique within the case.

    Channels are asked to number findings '{channel}_{index}', but models
    don't always comply: two channels can both emit 'economic_00' for different
    claims (seen in the first local-model runs, 2026-09-26). Reading findings
    from each channel's output, and prefixing the channel to any id that
    repeats, keeps every finding instead of silently dropping the later ones.
    """
    per_channel = [(c.get("channel_name", "unknown"), f)
                   for c in cmap.get("channel_outputs", []) for f in c.get("findings", [])]
    if not per_channel:  # an older map without channel outputs
        per_channel = [(None, f) for t in cmap.get("timeframe_impacts", [])
                       for key in ("harm_findings", "benefit_findings", "neutral_findings")
                       for f in t.get(key, [])]
    counts: dict[str, int] = {}
    for _, f in per_channel:
        counts[f["finding_id"]] = counts.get(f["finding_id"], 0) + 1
    seen, out = set(), []
    for channel, f in per_channel:
        fid = f["finding_id"]
        if counts[fid] > 1 and channel:
            fid = f"{channel}/{fid}"
        n, base = 2, fid
        while fid in seen:  # the same channel repeating an id
            fid, n = f"{base}#{n}", n + 1
        seen.add(fid)
        out.append(dict(f, finding_id=fid))
    return out


def _wrong_if(f: dict) -> str:
    groups = ", ".join(f.get("affected_groups") or []) or "the groups described"
    return (f"The {f['direction']} described does not occur for {groups}, or occurs at clearly "
            f"lower magnitude than stated ({f['magnitude']} on Arbitrator's 0-1 scale), "
            f"within the {f['timeframe'].replace('_', ' ')} window.")


def _compendium_identity(result: dict) -> str:
    comp = result.get("compendium")
    if not comp:
        return "not consulted"
    return comp.get("identity") or comp.get("version") or "consulted (version unknown)"


def _case_from_block(result: dict, *, arbitrator_version: str, code_version: str, question: str | None,
                     decision_makers: list | None, affected: list | None, today: date) -> dict:
    """A case for a run the Ethics Core stopped before any channel ran.

    A block is a recommendation too (don't do this), and if the decision-makers
    go ahead anyway, the look-back is exactly where it matters. It implies one
    checkable prediction: carried out, the action does more harm than good (or,
    for a hard reject, crosses the named constraints). The scores behind it are
    structural estimates from the parsed proposal, made before any model looked
    at it, and the case says so. If the action is never carried out, the
    prediction can only be marked unresolvable: the road not taken is never
    observed.
    """
    ev = result["ethics_evaluation"]
    verdict = ev.get("verdict", "unknown")
    constraints = ev.get("hard_constraints_triggered") or []
    scores = (f"weighted harm {ev.get('weighted_harm')}, weighted benefit {ev.get('weighted_benefit')}, "
              f"net {ev.get('net_score')}")
    horizon = ((result.get("manifest") or {}).get("context") or {}).get("time_horizon")
    horizon = horizon if horizon in CHECK_AFTER_DAYS else "short_term"

    if constraints:
        claim = ("Carried out as proposed, this action would cross these hard constraints: "
                 + "; ".join(constraints) + ".")
        wrong_if = ("The action is carried out as proposed and, judged by what is then observed, "
                    "crosses none of the named constraints.")
    else:
        claim = (f"Carried out as proposed, this action's harms would outweigh its benefits "
                 f"(Ethics Core structural estimate: {scores}).")
        wrong_if = ("The action is carried out as proposed, and its observed benefits to those affected "
                    f"clearly outweigh its harms within the {horizon.replace('_', ' ')} window.")
    wrong_if += " If the action is never carried out, this prediction can only be marked unresolvable."

    parts = [f"Arbitrator declined to analyse this proposal: its Ethics Core pre-screen returned "
             f"'{verdict}', and the pipeline stopped before any channel or model ran.",
             f"Justification: {ev.get('justification', '').strip()}",
             f"The scores ({scores}) are structural estimates derived from the parsed proposal, "
             "not the result of analysis."]
    if constraints:
        parts.append("Hard constraints triggered: " + "; ".join(constraints) + ".")
    if ev.get("flags"):
        parts.append("Flags: " + " ".join(ev["flags"]))

    return {
        "question": question or result.get("raw_input", ""),
        "recommender": {
            "system": "Arbitrator " + arbitrator_version,
            "model": "none: stopped by the Ethics Core (deterministic code) before any model was consulted",
            "code_version": code_version,
            "compendium_version": "not consulted (the run was stopped before the consultation)",
            "palaestra_lineage": "none",
        },
        "recommendation": " ".join(parts),
        "predictions": [{
            "id": "ethics_core_block",
            "claim": claim,
            "confidence": ev["confidence"] if "confidence" in ev else 0.5,
            "confidence_basis": ("the Ethics Core's self-reported confidence in its own structural evaluation; "
                                 "not a calibrated probability about the outcome") if "confidence" in ev
                                else "not reported by the Ethics Core; 0.5 recorded as no information",
            "wrong_if": wrong_if,
            "check_after": (today + timedelta(days=CHECK_AFTER_DAYS[horizon])).isoformat(),
            "derived_from": f"arbitrator ethics_core verdict '{verdict}' (the run was blocked)",
        }],
        "decision_makers": decision_makers or [],
        "affected": affected or [],
        "source": {"system": "arbitrator", "session_id": result.get("session_id"), "map_id": None,
                   "blocked": True, "stage": "ethics_core", "ethics_verdict": verdict,
                   "hard_constraints": constraints, "compendium_entries": []},
    }


def case_from_arbitrator(result: dict, *, arbitrator_version: str, code_version: str,
                         question: str | None = None, decision_makers: list | None = None,
                         affected: list | None = None, today: date | None = None) -> dict:
    """Build a case_opened body from an Arbitrator PipelineResult dict."""
    today = today or date.today()
    cmap = result.get("consequence_map") or {}
    if not cmap and result.get("status") == "ethics_blocked" and result.get("ethics_evaluation"):
        return _case_from_block(result, arbitrator_version=arbitrator_version, code_version=code_version,
                                question=question, decision_makers=decision_makers, affected=affected,
                                today=today)
    if not cmap:
        raise ValueError("this Arbitrator result has no consequence map (status "
                         f"{result.get('status')!r}); there is no recommendation to record")

    models = sorted({c.get("model_id") for c in cmap.get("channel_outputs", []) if c.get("model_id")})
    predictions, unscored = [], []
    for f in _findings(cmap):
        conf = CONFIDENCE.get(f["certainty"])
        if conf is None:
            unscored.append(f["summary"])
            continue
        predictions.append({
            "id": f["finding_id"],
            "claim": f["summary"],
            "confidence": conf,
            "confidence_basis": f"mapped from Arbitrator certainty '{f['certainty']}'",
            "wrong_if": _wrong_if(f),
            "check_after": (today + timedelta(days=CHECK_AFTER_DAYS[f["timeframe"]])).isoformat(),
            "derived_from": f"arbitrator finding {f['finding_id']}",
        })

    ethics = f"ethics: {result.get('ethics_verdict')}"
    if result.get("gate_mode") == "analysis":
        ethics = (f"ethics post-screen, from the analysis: {result.get('ethics_verdict')}; "
                  f"pre-screen, structural estimates: {result.get('prescreen_verdict')}")
    parts = [f"Arbitrator verdict: {cmap.get('overall_verdict')} ({ethics}).",
             cmap.get("executive_summary", "").strip()]
    if cmap.get("recommended_mitigations"):
        parts.append("Mitigations: " + "; ".join(cmap["recommended_mitigations"]))
    if unscored:
        parts.append("Findings of unknown certainty (not recorded as predictions): " + "; ".join(unscored))

    body = {
        "question": question or result.get("raw_input") or cmap.get("proposal_description", ""),
        "recommender": {
            "system": "Arbitrator " + arbitrator_version,
            "model": ", ".join(models) or "unknown",
            "code_version": code_version,
            "compendium_version": _compendium_identity(result),
            "palaestra_lineage": "none",
        },
        "recommendation": " ".join(p for p in parts if p),
        "predictions": predictions,
        "decision_makers": decision_makers or [],
        "affected": affected or [],
        "source": {"system": "arbitrator", "session_id": result.get("session_id"),
                   "map_id": cmap.get("map_id"),
                   "compendium_entries": [e["id"] for e in (result.get("compendium") or {}).get("selected", [])]},
    }
    _add_brief(body, result.get("brief"), result.get("escalation"))
    return body


def _add_brief(body: dict, written: dict | None, esc: dict | None) -> None:
    """The run's escalation (what triggered human review, if anything) and its
    decision brief. Every analysed run has a brief (since 2026-09-29); its
    options and provisional lean become the case's options and recommended
    option, so a decision recorded later can say it followed the lean or
    departed from it."""
    if esc and esc.get("triggers"):
        body["escalation"] = {"triggers": esc["triggers"]}
    if not written:
        return
    brief = written.get("brief")
    record = {"brief_by": written.get("model_id"), "brief_error": written.get("error")}
    if brief:
        record.update({k: brief.get(k) for k in (
            "why_human_judgment", "disagreements", "case_for", "case_against", "uncertainties",
            "decision_questions", "provisional_lean", "set_aside", "review")})
        body["options"] = [{
            "id": str(o["id"]).strip(),
            "label": str(o["label"]).strip(),
            "description": " ".join(p for p in (
                str(o.get("consequences") or "").strip(),
                f"Who bears the cost: {o['who_bears_cost']}." if o.get("who_bears_cost") else "",
                {True: "Reversible.", False: "Not reversible."}.get(o.get("reversible"), ""),
                f"For: {o['case_for']}" if o.get("case_for") else "",
                f"Against: {o['case_against']}" if o.get("case_against") else "",
            ) if p),
        } for o in brief["options"]]
        lean = brief.get("provisional_lean") or {}
        if lean.get("option") in {o["id"] for o in body["options"]}:
            body["recommended_option"] = lean["option"]
            body["recommendation"] += (
                f" Decision brief: provisional lean '{lean['option']}' (confidence {lean.get('confidence')}). "
                f"{lean.get('reasoning') or ''} It would change if: {lean.get('would_change_if')}")
    body["brief"] = record
