"""
identity.py — Who is named in the record, and who is not.

The rule is decided at write time, because nothing can be erased later:

- Anyone with authority to change the outcome is named, in the role they
  held at the time ("J. Smith, as housing commissioner, 2027"). That
  includes dissenting votes: who argued for what is part of the record.
- Everyone else (affected people, people who carried a decision out, people
  who testify) is pseudonymous by default. They may choose to be named,
  and that choice is recorded as theirs.
- A system that shaped a decision is named precisely: which system, which
  model, which code, which Compendium, which Palaestra training. "The AI
  recommended it" is how accountability dissolves into the machine.

Person dicts accept only known keys, so identifying details can't ride
along in an unchecked field.
"""

from __future__ import annotations

import secrets

PERSON_KEYS = {"authority", "name", "role", "as_of", "pseudonym", "named_by_choice", "position"}
POSITIONS = ("decided", "for", "against", "abstained")
SYSTEM_KEYS = ("system", "model", "code_version", "compendium_version", "palaestra_lineage")


def new_pseudonym() -> str:
    return "p-" + secrets.token_hex(4)


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_person(p, where: str, *, require_authority: bool = False) -> tuple[dict, list[str]]:
    """Validate a person and return it normalized (a pseudonym assigned if one is due)."""
    if not isinstance(p, dict):
        return p, [f"{where}: a person must be an object"]
    errs = []
    unknown = set(p) - PERSON_KEYS
    if unknown:
        errs.append(f"{where}: unknown person fields {sorted(unknown)} (allowed: {sorted(PERSON_KEYS)})")
    if not isinstance(p.get("authority"), bool):
        errs.append(f"{where}: 'authority' must be true or false: could this person change the outcome?")
        return p, errs
    if not _text(p.get("role")):
        errs.append(f"{where}: 'role' is required")
    if "position" in p and p["position"] not in POSITIONS:
        errs.append(f"{where}: position {p['position']!r} not in {POSITIONS}")

    out = dict(p)
    if p["authority"]:
        if not _text(p.get("name")):
            errs.append(f"{where}: a person with authority to change the outcome is named")
        if not _text(p.get("as_of")):
            errs.append(f"{where}: 'as_of' is required for a named decision-maker (when they held the role)")
        if "pseudonym" in p:
            errs.append(f"{where}: a person with authority to change the outcome can't be pseudonymous")
    else:
        if require_authority:
            errs.append(f"{where}: only people with authority to change the outcome belong here")
        if "name" in p and not p.get("named_by_choice"):
            errs.append(
                f"{where}: people without authority over the outcome are pseudonymous; "
                "set named_by_choice only if they chose to be named"
            )
        if p.get("named_by_choice") and not _text(p.get("name")):
            errs.append(f"{where}: named_by_choice is set but no name was given")
        if not p.get("named_by_choice") and not _text(p.get("pseudonym")):
            out["pseudonym"] = new_pseudonym()
    return out, errs


def check_system(s, where: str) -> list[str]:
    if not isinstance(s, dict):
        return [f"{where}: a system identity must be an object"]
    errs = []
    for k in SYSTEM_KEYS:
        v = s.get(k)
        if k == "palaestra_lineage":
            if not (isinstance(v, list) and all(_text(x) for x in v)) and v != "none":
                errs.append(f"{where}: palaestra_lineage must be a list of run names, or \"none\"")
        elif not _text(v):
            errs.append(f"{where}: {k!r} is required (say \"unknown\" or \"not consulted\" if so; never leave it out)")
    return errs


def check_author(a, where: str) -> tuple[dict, list[str]]:
    """An author is a system identity (has 'system') or a person."""
    if isinstance(a, dict) and "system" in a:
        return a, check_system(a, where)
    return check_person(a, where)


def display(p: dict) -> str:
    if "system" in p:
        lineage = p["palaestra_lineage"]
        lineage = ", ".join(lineage) if isinstance(lineage, list) else lineage
        return (f"{p['system']} [model {p['model']}; code {p['code_version']}; "
                f"compendium {p['compendium_version']}; palaestra {lineage}]")
    if p.get("name"):
        s = f"{p['name']}, as {p['role']}"
        return s + (f", {p['as_of']}" if p.get("as_of") else "")
    return f"{p['pseudonym']} ({p['role']})"
