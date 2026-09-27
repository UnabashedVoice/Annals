"""
intake.py — Opening a case from an Arbitrator run.

Arbitrator produces a consequence map, not a list of predictions. Each
finding in it is a claim about the future, though: this group, this effect,
in this timeframe, with this certainty. Intake turns each finding into a
prediction and locks it, so that when the timeframe comes round there is
something specific to check.

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


def case_from_arbitrator(result: dict, *, arbitrator_version: str, code_version: str,
                         question: str | None = None, decision_makers: list | None = None,
                         affected: list | None = None, today: date | None = None) -> dict:
    """Build a case_opened body from an Arbitrator PipelineResult dict."""
    today = today or date.today()
    cmap = result.get("consequence_map") or {}
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

    parts = [f"Arbitrator verdict: {cmap.get('overall_verdict')} "
             f"(ethics: {result.get('ethics_verdict')}).", cmap.get("executive_summary", "").strip()]
    if cmap.get("recommended_mitigations"):
        parts.append("Mitigations: " + "; ".join(cmap["recommended_mitigations"]))
    if unscored:
        parts.append("Findings of unknown certainty (not recorded as predictions): " + "; ".join(unscored))

    return {
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
