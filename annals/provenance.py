"""
provenance.py — Pinning down exactly which mind made a recommendation.

A recommender is named by the system, its model, its code, the Compendium
it drew on, and the Palaestra runs it trained in. These helpers compute the
parts that can be computed. What can't be known is written as "unknown",
and what wasn't used as "not consulted": the record states the gap rather
than leaving a blank that reads as nothing to say.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def git_version(repo: str | Path) -> str:
    """Commit hash, with -dirty if the working tree has uncommitted changes."""
    try:
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return commit[:12] + ("-dirty" if dirty else "")


def compendium_version(compendium_root: str | Path) -> str:
    """Content hash of the built corpus (dist/compendium.jsonl): what a model could actually have read."""
    built = Path(compendium_root) / "dist" / "compendium.jsonl"
    if not built.exists():
        return "unknown (no built corpus at dist/compendium.jsonl)"
    return "sha256:" + hashlib.sha256(built.read_bytes()).hexdigest()[:16]


def compendium_entry_ids(compendium_root: str | Path) -> set[str]:
    """Entry ids that exist, read from filenames (SCHEMA.md: the file is named <id>.md)."""
    return {p.stem for p in (Path(compendium_root) / "entries").glob("*/*.md")}
