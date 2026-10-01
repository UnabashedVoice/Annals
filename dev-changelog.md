# Annals — Development Timeline & Changelog

Annals (`github.com/UnabashedVoice/Annals`) is the fifth component of the stack. It is an append-only, hash-chained record of **what was recommended, what was decided and what happened**. It is the feedback loop that brings the world back into an otherwise closed system: Arbitrator's recommendations are checked against what actually followed, and the lessons flow back to Palaestra, Actualizer and the Compendium. The guiding line is *"History isn't learned if it is rewritten."*

> **How this was compiled (2026-09-27).** From git history (2 commits), the README, module timestamps, the working-tree diff, project notes from the 2026-09-24/25 design sessions, and the test record and logs in `../system_runs/2026-09-26-five-question/`. The 2026-09-26 work, uncommitted when this was compiled, was committed and pushed on 2026-09-27.

---

## Timeline at a glance

| Date / time | Milestone |
|---|---|
| 2026-09-24 | Named and designed with the user as the fifth component |
| 2026-09-24 23:59 – 09-25 00:02 | Core modules written (`entries`, `cases`, `identity`, `record`, `render`, `provenance`, `intake`, `exports`, `cli`) |
| 2026-09-25 00:10 | `dc01dc9` initial commit, with matching wiring commits in Arbitrator, Actualizer and Palaestra at the same second. Published on GitHub |
| 2026-09-25 10:44 | `7fb86a7` UTF-8 console guard (30 tests) |
| 2026-09-26 | Compendium identity in intake, a fix for colliding finding ids, the "nothing observed yet" evidence header (33 tests). First real use: a 5-question batch writing to a test record (committed 2026-09-27) |
| 2026-09-28 → 09-29 | Ethics-blocked Arbitrator runs recorded as cases; escalation and decision brief as separate case fields (38 tests; committed 2026-10-01, alongside Arbitrator-AI `02088c0`) |

---

## 2026-09-28 to 09-29 (committed 2026-10-01)

### Added
- **Ethics-blocked Arbitrator runs are recorded** (`intake._case_from_block`). This was the user's decision, 2026-09-28: a block is a recommendation too.
  - Recommender: `model` says none was consulted, and `compendium_version` says the run stopped before the consultation.
  - One prediction, `ethics_core_block`: carried out, the action does more harm than good, with the Ethics Core's weighted harm, benefit and net score. For a hard reject, the prediction is that it crosses the named constraints.
  - `wrong_if` says the prediction can only be marked unresolvable if the action is never carried out. `check_after` comes from the parsed time horizon. Confidence is the Ethics Core's own, labeled as not a calibrated probability.
  - `source.blocked`, `stage`, `ethics_verdict` and `hard_constraints` mark the case.
  - Checked end to end through the real `arbitrator run --annals` on default settings (q5, the seawall tax, is blocked at the pre-screen). The Palaestra and Actualizer exports handle blocked cases. 35 tests.

- **Escalation and brief are separate case fields** (2026-09-29).
  - `escalation` now holds only what triggered human review.
  - `brief` holds the decision brief, which every analysed run now has. Its options carry their cases for and against, and the recommendation gives the lean's reasoning.
  - `render_case` shows both sections. 38 tests.

## 2026-09-26: Compendium wiring (committed 2026-09-27)

4 files changed (+92/−12), found while verifying the Annals against the first real local-model runs through the whole stack.

### Fixed
- **Intake silently dropped findings whose ids collided across channels** (`intake._findings`).
  - Channels are asked to number findings `{channel}_{index}`, but local models don't always comply. Two channels both emitted `economic_00` for different claims, and intake de-duplicated by id, so the later finding was lost.
  - Findings are now read per channel from `channel_outputs`. Any id that repeats gets its channel as a prefix (`geopolitical/economic_00`), and repeats within one channel get `#2`, `#3`.
  - Older maps without `channel_outputs` fall back to `timeframe_impacts`.
- **Actualizer evidence could be read as observed fact.**
  - In the first real run (2026-09-26), a deliberating model read a locked *prediction* as "evidence from the case shows…". The only hint otherwise was a "(nothing observed yet)" line at the very bottom.
  - `exports.actualizer_evidence()` now puts **"NOTHING HAS BEEN OBSERVED YET IN THIS CASE"** at the top of any case with no outcomes, and also says "no decision" when there isn't one. It states that every effect claim below is a prediction.
  - An A/B check (`system_runs/…/evidence_header_check.log`, 3 samples per header) was inconclusive about the effect on stance at n=3.

### Added
- **The Compendium in the recommender's identity.**
  - `compendium_version` is now filled from the run's consultation, e.g. `compendium f0907b559bcb (35 entries); consulted: kant-formula-of-humanity`, instead of the hard-coded `not consulted`. A run that didn't consult the Compendium still writes `not consulted` in full.
  - `source.compendium_entries` lists the chosen entry ids.
- README updated: Arbitrator → Annals intake describes the Compendium identity; "Not built yet" now says Arbitrator *does* read the Compendium with `--compendium`, and only Palaestra training remains unbuilt.
- 3 new tests (33 in total): colliding ids are kept, the Compendium consultation is named, and predictions-only evidence says so first.

### First real use
- `system_runs/2026-09-26-five-question/annals_test_record.jsonl` is a separate **test** record, never the Annals' own, because test cases written to an append-only record could never be removed.
- It holds 17 cases from `arbitrator run --annals --annals-record …`: gpt-oss-20b 15/15 and qwen3-32b in progress. Each case names the model with its identity key, and names the Compendium build and the entries it chose.
- Found in that run: **an Arbitrator run blocked by the Ethics Core has no consequence map, so it can't be recorded.** `intake` refuses a run with no map, by design.

---

## 2026-09-25

### `7fb86a7` — Reconfigure stdout/stderr to UTF-8 in `main()`
- Entries carry free text (recommendations, testimony, reviewers' reasoning), and `show` and `export` print it back. Added the same hasattr-guarded, exception-swallowing guard Arbitrator and Actualizer use. 30/30 tests pass.

### `dc01dc9` — Annals: an append-only record of recommendations and what followed
14 files, +1,628 lines, standard library only.

**Design commitments** (agreed with the user on 2026-09-24)
- **The prediction is locked before the outcome.** A case opens with an expected outcome, a confidence and a `wrong_if` falsifier. A later `prediction_added` is accepted, but it is stamped with how many decisions and outcomes were already known when it was made.
- **Three columns: recommended, decided, happened.** The decision's relation to the recommendation is recorded as `followed`, `partially_followed`, `departed` or `no_decision`. Counterfactuals are never recorded, and there is no field for them.
- **Reasoning is judged apart from the outcome**, to avoid judging a decision by its result. Reviews judge reasoning as `sound`, `flawed`, `mixed` or `cannot_judge`, record what we failed to know, and flag the two cells most easily misread: sound reasoning with a bad outcome, and flawed reasoning rescued by luck.
- **Many voices.** Affected people add `testimony`, modelled on M&M conferences and aviation incident reports. Descendants can annotate any entry later.
- **Append-only and hash-chained.** Corrections are `annotation`s pointing at the old entry. `verify` locates any break, and appends are refused until it is resolved. `recorded_at` is always the writer's clock.

**Who is named** (`identity.py`)
- Anyone with authority to change the outcome is named in their role at the time, dissenting votes included.
- Everyone else is pseudonymous by default (`p-xxxxxxxx`), assigned at write time so nothing ever needs erasing. They can choose to be named.
- The recommender is named precisely: system, model, code version, Compendium version and Palaestra lineage. "Unknown" and "not consulted" must be written out, never left blank.
- Reviewers are named.
- Person entries accept only whitelisted fields.

**Modules**
- `entries.py`: seven entry kinds (`case_opened`, `prediction_added`, `decision_recorded`, `outcome_observed`, `testimony`, `review`, `annotation`) with validation. `outcome_observed` is refused until a decision exists.
- `record.py`: the hash-chained store (`record/annals.jsonl`, `$ANNALS_RECORD` or `--record`), `verify`, `head`, and `verify --anchor` for checking against externally published heads.
- `cases.py`, `render.py` and `provenance.py`.
- `intake.py`: **Arbitrator → Annals.**
  - Consequence-map findings become predictions. Confidence comes from the certainty label (high 0.85, moderate 0.6, low 0.3), and `check_after` is the earliest date the timeframe allows.
  - `unknown`-certainty findings go into the recommendation text instead of becoming predictions.
  - Available as `intake-arbitrator result.json`, or driven from Arbitrator's `run --annals`.
- `exports.py`:
  - **→ Palaestra:** a draft scenario family with an `_authoring` to-do list. Palaestra refuses the draft until the list is done, and the outcome goes in a `source` block the agent never sees.
  - **→ Actualizer:** an evidence packet with the header "evidence, not an instruction" and the reference `annals:<case>@<record head>`.
  - **→ Compendium:** `challenges` lists the entries that reviews say a gap bears on, and flags ids that don't exist yet. Nothing is written into the corpus ("case law tests statute").
- `cli.py`: `add`, `list`, `show`, `due`, `verify`, `head`, `export`, `challenges`, `intake-arbitrator`.
- `tests/test_annals.py`: 30 tests.

**Sibling wiring committed at the same moment (00:10:26)**
- Arbitrator `5d66bf3` (`run --annals`), Actualizer `6ced6de` (`DeliberationGate(evidence=…)`) and Palaestra `a16df35` (families from Annals cases).

---

## 2026-09-24 — Named and designed
- Proposed as the fifth piece, alongside Arbitrator, Actualizer, Palaestra and the Compendium. Without real outcomes, the stack only grows more self-consistent and never checks itself against the world.
- The framing the user accepted: the system aims at decisions **descendants can still change** (optionality and reversibility), not a world optimized to present values. The "future generations" justification is itself flagged as a risk across the whole stack, because it has the same shape as the core fear Actualizer guards against.
- The identity principle, in the user's words: *"the record never changes, so be deliberate about what goes into it."*

---

## Open items (README "Not built yet")
- **Sealed entries:** predictions written now but readable only after a set date. The question of who holds the seal is still open.
- **Arbitrator training in Palaestra:** not built. The identity correctly says `palaestra: none`.
- **Better falsifiers:** Arbitrator's derived `wrong_if` is generic.
- **Cross-process locking:** two writers appending at once aren't guarded against; the chain would detect the damage but not prevent it.
- **Ethics-blocked runs:** a run the Ethics Core blocks can't currently be recorded.
