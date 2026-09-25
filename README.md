# Annals

The record of what was recommended, what was decided, and what happened.

The Annals are the feedback loop for four sibling projects. **Arbitrator** advises decision-makers. **Actualizer** helps a mind deliberate about changing itself. **Palaestra** is where agents practise decisions. The **Compendium** is the philosophy they draw on. Without the Annals the four form a closed system: it can grow more internally consistent while drifting away from the world. The Annals bring the world back in. Arbitrator's recommendations are checked against what actually followed, and the lessons go back to the other three.

Annals were records kept year by year and never revised. This one works the same way: it is append-only, and nothing in it is ever edited. History isn't learned if it is rewritten.

**Requirements.** Python 3.10+, standard library only.

## Design commitments

- **The prediction is locked before the outcome.** A case opens with what the recommender expected, how confident it was, and what result would prove it wrong (`wrong_if`), before anyone knows how it turns out. A prediction made later is still accepted, but the record stamps it with how many decisions and outcomes were already known when it was made, so it can never pass for one that came first.
- **Three columns, not two.** *Recommended*, *decided* and *happened* are recorded separately. Decision-makers don't always follow the advice, and the record says how the decision relates to the recommendation (`followed / partially_followed / departed / no_decision`). What would have happened on the road not taken is never recorded, because it was never observed. There's no field for it.
- **Reasoning is judged apart from the outcome.** A review answers two questions: was the reasoning sound given what was knowable then, and what did we fail to know? The case view puts the reasoning judgment beside the outcomes without merging them. It also flags the two cells that are easiest to misread: sound reasoning that met a bad outcome, and flawed reasoning rescued by luck.
- **Many voices.** People affected by a decision add their own accounts (`testimony`). Later generations can annotate any entry. That is how the people who inherit a decision eventually get a voice in it.
- **Append-only, hash-chained.** Each entry carries the hash of the one before it. Editing, removing or reordering any entry breaks the chain, `verify` says where, and nothing more can be appended until it's resolved. A correction is a new `annotation` that points at the old entry, and the old entry stays as written.
- **Deliberate about what goes in.** Because nothing can be erased, identities are decided when an entry is written. See below.

## Who is named

| Who | In the record |
|---|---|
| Anyone with **authority to change the outcome**, including dissenting votes | Named, in the role held at the time: *J. Smith, as housing commissioner, 2027* |
| Everyone else: affected people, people who carried a decision out, people who testify | Pseudonymous by default (`p-3f9a1c2e`, assigned at write time). They may choose to be named (`named_by_choice`). |
| The **recommending system** | Named precisely: system, model, code version, Compendium version, Palaestra lineage. "Unknown" and "not consulted" must be written out, never left blank. |
| **Reviewers** | Named. A judgment of someone's reasoning carries the reviewer's name. |

A person entry accepts only known fields (`authority, name, role, as_of, pseudonym, named_by_choice, position`), so identifying details can't be slipped into an unchecked field. Free text (accounts, observations) is not scanned for names, so whoever writes it has to check.

## Entry kinds

| Kind | What it records |
|---|---|
| `case_opened` | The question, the recommender, the recommendation, options, predictions (each with `confidence`, `wrong_if`, `check_after`), who it was addressed to, who is affected |
| `prediction_added` | A later prediction, stamped with what was already known |
| `decision_recorded` | What was decided, how it relates to the recommendation, and every decider with their position (`decided / for / against / abstained`) |
| `outcome_observed` | What happened against one prediction (`held / failed / mixed / too_early / unresolvable`), or something nobody predicted (`unanticipated`). Refused until a decision is recorded, because outcomes follow from what was decided. |
| `testimony` | An account from someone affected |
| `review` | Reasoning `sound / flawed / mixed / cannot_judge`, the basis for that, and the gaps: what we failed to know, which Compendium entries it bears on, and whether it's worth a Palaestra scenario |
| `annotation` | A `note`, `correction`, `context` or `descendant` reply on any earlier entry |

`recorded_at` is always the clock at the moment of writing and can't be supplied by the writer. Dates that belong to the world (`observed_on`, `check_after`) are separate fields.

## How it connects

```
 Arbitrator ──run --annals──▶ ANNALS ──export palaestra──▶ Palaestra (draft scenario; outcome hidden from the agent)
                               │  ├───export actualizer──▶ Actualizer (evidence in a deliberation)
                               │  └───challenges─────────▶ Compendium (entries a gap bears on)
     decision-makers,  ────────┘
     affected people, reviewers, descendants
```

- **Arbitrator → Annals.** `arbitrator run --annals` opens a case from the run. Each finding in the consequence map becomes a prediction. Its confidence is mapped from the finding's certainty label (`high` 0.85, `moderate` 0.6, `low` 0.3), and `check_after` is the earliest date its timeframe allows it to be judged. Each prediction says it was derived this way. Findings of `unknown` certainty aren't turned into predictions; they're listed in the recommendation instead. The same intake is available from this side as `annals intake-arbitrator result.json`, for a result saved with `arbitrator run --json -o`.
- **Annals → Palaestra.** `annals export palaestra CASE` writes a draft scenario family. Only a person can author the effects on every party, each tradition's reading and the shapes, so the draft carries what the case knows plus a to-do list, and Palaestra refuses to load it until the list is done. What actually happened goes in the family's `source`. The agent never sees it. Palaestra's report shows it beside the agent's choice afterwards, with the reminder that the observed outcome of one option says nothing about the others.
- **Annals → Actualizer.** `annals export actualizer CASE` gives an evidence packet: the case as recorded, under a header saying it is evidence rather than an instruction. `DeliberationGate.propose_and_commit(..., evidence=[packet])` shows it to the mind after the dossier. The packet's reference, `annals:<case>@<record head>`, is kept on the committed `DeliberationRecord`. The record supplies the case, and the mind rules on it.
- **Annals → Compendium.** `annals challenges` lists the Compendium entries that reviews say a gap bears on, and flags the ones not yet written. It works the way case law tests a statute: nothing is written into the corpus, and the boundary between empirical record and philosophy stays clean.

## Usage

```bash
python -m annals add case_opened open.json        # {"author": {...}, "body": {...}}
python -m annals add decision_recorded decision.json
python -m annals list
python -m annals show <case_id>
python -m annals due                              # predictions whose time to check has come
python -m annals verify
python -m annals head                             # publish this line somewhere outside your control
python -m annals export palaestra <case_id> --out ../Palaestra/scenarios/drafts/<case_id>.json
python -m annals export actualizer <case_id> --out evidence.json
python -m annals challenges
python -m unittest discover -s tests
```

The record lives at `record/annals.jsonl` (or `$ANNALS_RECORD`, or `--record`). There's no edit or delete command, because there's no edit or delete.

## What the chain does and doesn't prove

The hash chain proves order and integrity *within* the file. It can't prove the file wasn't written all at once, later, with invented dates. For that, publish the output of `annals head` from time to time somewhere outside the record-keeper's control. A commit to a public repository is enough. Anyone holding an old head hash can then check that the record they're shown still contains it: `annals verify --anchor <hash>`.

## Not built yet

- **Sealed entries.** Predictions written now but readable only after a set date, for decisions whose real results come a generation later. This fits the immutability principle but raises a trust question: someone has to hold the seal.
- **Arbitrator reading the Compendium or training in Palaestra.** Until it does, its recorded identity says `compendium: not consulted` and `palaestra: none`, which is accurate.
- **Better falsifiers from Arbitrator.** The `wrong_if` written for derived predictions is generic ("the stated harm does not occur at the stated magnitude within the window"). A recommender that states its own falsifiers would make the look-back sharper.
- **Cross-process locking.** Appends are safe within one process. Two processes writing the same record at once are not guarded against. The chain would detect the damage, but not prevent it.
