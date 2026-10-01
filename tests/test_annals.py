import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from annals import Annals, RecordError, RecordIntegrityError
from annals.cli import main
from annals.exports import actualizer_evidence, compendium_challenges, palaestra_draft
from annals.intake import case_from_arbitrator
from annals.render import render_case

ARBITRATOR = {"system": "Arbitrator 0.1.0", "model": "gpt-oss-20b", "code_version": "83b9e1b",
              "compendium_version": "not consulted", "palaestra_lineage": "none"}
COMMISSIONER = {"authority": True, "name": "J. Smith", "role": "housing commissioner", "as_of": "2027"}
REVIEWER = {"authority": True, "name": "R. Reyes", "role": "Annals reviewer", "as_of": "2030"}


def opened(**over):
    body = {
        "question": "Should the district's water allocation be cut 30% by relocating the lowest-income households?",
        "recommender": ARBITRATOR,
        "recommendation": "Do not relocate; tiered pricing with a protected baseline.",
        "recommended_option": "tiered",
        "options": [{"id": "relocate", "label": "Relocate"}, {"id": "tiered", "label": "Tiered pricing"},
                    {"id": "flat", "label": "Flat cut"}],
        "predictions": [{"id": "p1", "claim": "Use falls 30% within two years.", "confidence": 0.6,
                         "wrong_if": "Use falls less than 20% by the check date.", "check_after": "2029-01-01"}],
        "decision_makers": [COMMISSIONER],
        "affected": [{"description": "Households in the lowest-income district", "kind": "human_group"}],
    }
    body.update(over)
    return body


def decided(case_id, **over):
    body = {"case_id": case_id, "decided": "Relocation, phased over three years.", "option": "relocate",
            "relation": "departed",
            "deciders": [dict(COMMISSIONER, position="decided"),
                         {"authority": True, "name": "A. Okafor", "role": "council member", "as_of": "2027",
                          "position": "against"}]}
    body.update(over)
    return body


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "annals.jsonl"
        self.a = Annals(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def open_case(self, **over):
        return self.a.append("case_opened", opened(**over), ARBITRATOR)["body"]["case_id"]

    def refused(self, kind, body, author, fragment):
        with self.assertRaises(RecordError) as cm:
            self.a.append(kind, body, author)
        self.assertIn(fragment, str(cm.exception))


class TestLifecycle(Base):
    def test_full_case_reads_as_three_columns(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.a.append("outcome_observed", {"case_id": cid, "prediction_id": "p1", "result": "held",
                                           "observed": "Use fell 31%.", "observed_on": "2029-03-01"}, REVIEWER)
        self.a.append("outcome_observed", {"case_id": cid, "prediction_id": None, "result": "unanticipated",
                                           "observed": "The relocated cooperative dissolved.",
                                           "observed_on": "2029-06-01"}, REVIEWER)
        self.a.append("review", {"case_id": cid, "reasoning": "sound",
                                 "reasoning_basis": "Given the hydrology known in 2027, the prediction was reasonable.",
                                 "gaps": [{"gap": "Cooperative cohesion depended on land tenure.",
                                           "compendium_entries": ["aristotle-political-animal"], "palaestra": True}]},
                      REVIEWER)
        text = render_case(self.a.case(cid))
        for part in ("RECOMMENDED", "DECIDED", "HAPPENED", "LOOK-BACK", "J. Smith, as housing commissioner, 2027",
                     "A. Okafor, as council member, 2027: against", "road not taken is unobserved",
                     "Sound reasoning, outcome missed"):
            self.assertIn(part, text)

    def test_reopening_reads_the_same_record(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        again = Annals(self.path)
        self.assertEqual(again.problems, [])
        self.assertEqual(len(again.case(cid).decisions), 1)
        self.assertEqual(again.head(), self.a.head())

    def test_writer_cannot_set_recorded_at(self):
        self.refused("case_opened", opened(recorded_at="2020-01-01"), ARBITRATOR, "unknown fields")

    def test_caller_mutation_does_not_reach_the_record(self):
        body = opened()
        cid = self.a.append("case_opened", body, ARBITRATOR)["body"]["case_id"]
        body["predictions"][0]["claim"] = "rewritten"
        self.assertEqual(self.a.case(cid).predictions["p1"]["prediction"]["claim"], "Use falls 30% within two years.")
        self.assertEqual(self.a.verify(), [])


class TestPredictions(Base):
    def test_prediction_needs_a_falsifier(self):
        preds = [{"id": "p1", "claim": "Things improve.", "confidence": 0.9, "check_after": "2030-01-01"}]
        self.refused("case_opened", opened(predictions=preds), ARBITRATOR, "wrong_if")

    def test_a_recommendation_must_predict_something(self):
        self.refused("case_opened", opened(predictions=[]), ARBITRATOR, "at least one prediction")

    def test_late_prediction_is_stamped_with_what_was_known(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.a.append("prediction_added", {"case_id": cid, "prediction": {
            "id": "p2", "claim": "Aquifer stabilizes.", "confidence": 0.5, "wrong_if": "Levels keep falling.",
            "check_after": "2031-01-01"}}, ARBITRATOR)
        late = self.a.case(cid).predictions["p2"]["late"]
        self.assertEqual(late, {"decisions_recorded": 1, "outcomes_observed": 0})
        self.assertIn("after 1 decision(s)", render_case(self.a.case(cid)))

    def test_outcome_waits_for_a_decision(self):
        cid = self.open_case()
        self.refused("outcome_observed", {"case_id": cid, "prediction_id": "p1", "result": "held",
                                          "observed": "x", "observed_on": "2029-01-01"}, REVIEWER,
                     "record the decision first")

    def test_unanticipated_belongs_to_no_prediction(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.refused("outcome_observed", {"case_id": cid, "prediction_id": "p1", "result": "unanticipated",
                                          "observed": "x", "observed_on": "2029-01-01"}, REVIEWER,
                     "belongs to no prediction")

    def test_due(self):
        cid = self.open_case()
        case = self.a.case(cid)
        self.assertEqual(case.due(date(2028, 12, 31)), [])
        self.assertEqual(case.due(date(2029, 1, 1)), ["p1"])
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.a.append("outcome_observed", {"case_id": cid, "prediction_id": "p1", "result": "too_early",
                                           "observed": "Not yet.", "observed_on": "2029-01-02"}, REVIEWER)
        self.assertEqual(case.due(date(2029, 2, 1)), ["p1"])


class TestIdentity(Base):
    def test_decision_makers_are_named(self):
        anon = {"authority": True, "role": "housing commissioner", "as_of": "2027"}
        self.refused("case_opened", opened(decision_makers=[anon]), ARBITRATOR, "is named")

    def test_decision_makers_cannot_hide_behind_a_pseudonym(self):
        self.refused("case_opened", opened(decision_makers=[dict(COMMISSIONER, pseudonym="p-1234")]),
                     ARBITRATOR, "can't be pseudonymous")

    def test_deciders_must_have_authority(self):
        cid = self.open_case()
        clerk = {"authority": False, "role": "clerk who filed the order", "position": "decided"}
        self.refused("decision_recorded", decided(cid, deciders=[clerk]), COMMISSIONER, "only people with authority")

    def test_decider_position_required(self):
        cid = self.open_case()
        self.refused("decision_recorded", decided(cid, deciders=[COMMISSIONER]), COMMISSIONER, "'position' is required")

    def test_testifier_is_pseudonymous_by_default(self):
        cid = self.open_case()
        e = self.a.append("testimony", {"case_id": cid, "account": "We lost the farm.",
                                        "teller": {"authority": False, "role": "relocated household"}},
                          {"authority": False, "role": "relocated household"})
        self.assertTrue(e["body"]["teller"]["pseudonym"].startswith("p-"))
        self.assertNotIn("name", e["body"]["teller"])

    def test_testifier_name_refused_unless_chosen(self):
        cid = self.open_case()
        teller = {"authority": False, "role": "relocated household", "name": "M. Diaz"}
        self.refused("testimony", {"case_id": cid, "account": "x", "teller": teller}, REVIEWER, "pseudonymous")
        e = self.a.append("testimony", {"case_id": cid, "account": "x",
                                        "teller": dict(teller, named_by_choice=True)}, REVIEWER)
        self.assertEqual(e["body"]["teller"]["name"], "M. Diaz")

    def test_no_identifying_side_fields(self):
        cid = self.open_case()
        teller = {"authority": False, "role": "household", "email": "someone@example.org"}
        self.refused("testimony", {"case_id": cid, "account": "x", "teller": teller}, REVIEWER, "unknown person fields")

    def test_recommender_identity_is_complete(self):
        partial = {k: v for k, v in ARBITRATOR.items() if k != "compendium_version"}
        self.refused("case_opened", opened(recommender=partial), ARBITRATOR, "compendium_version")

    def test_reviews_are_signed(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.refused("review", {"case_id": cid, "reasoning": "flawed", "reasoning_basis": "x"},
                     {"authority": False, "role": "anonymous critic"}, "named reviewer")


class TestImmutability(Base):
    def test_annotation_leaves_target_as_written(self):
        cid = self.open_case()
        target = self.a.case(cid).opened
        before = json.dumps(target, sort_keys=True)
        self.a.append("annotation", {"target": target["entry_id"], "kind": "descendant",
                                     "text": "We live with this now."}, {"authority": False, "role": "resident, 2071"})
        self.assertEqual(json.dumps(self.a.case(cid).opened, sort_keys=True), before)
        self.assertEqual(len(self.a.case(cid).annotations), 1)

    def test_edit_is_detected_and_blocks_appends(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace("Use falls 30%", "Use falls 10%")
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tampered = Annals(self.path)
        self.assertTrue(any("edited after writing" in p for p in tampered.problems))
        with self.assertRaises(RecordIntegrityError):
            tampered.append("annotation", {"target": tampered.entries()[0]["entry_id"], "kind": "note",
                                           "text": "x"}, REVIEWER)

    def test_removal_is_detected(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.a.append("testimony", {"case_id": cid, "account": "x", "teller": {"authority": False, "role": "r"}}, REVIEWER)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        del lines[1]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertTrue(Annals(self.path).problems)

    def test_partial_write_is_reported(self):
        self.open_case()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write('{"seq": 1, "kind": "trunc')
        self.assertTrue(any("partial write" in p for p in Annals(self.path).problems))


class TestIntakeAndExports(Base):
    RESULT = {
        "session_id": "s-1", "status": "success", "raw_input": "Relocate the lowest-income district.",
        "ethics_verdict": "escalate",
        "consequence_map": {
            "map_id": "m-1", "overall_verdict": "net_harmful", "executive_summary": "Large harms to relocated households.",
            "recommended_mitigations": ["Tiered pricing instead"],
            "channel_outputs": [{"model_id": "gpt-oss-20b"}, {"model_id": "qwen3-32b"}],
            "timeframe_impacts": [{"timeframe": "short_term", "harm_findings": [
                {"finding_id": "social_00", "summary": "Relocated households lose income.", "direction": "harm",
                 "timeframe": "short_term", "certainty": "high", "magnitude": 0.7, "affected_groups": ["relocated households"]},
                {"finding_id": "social_01", "summary": "Unclear civic effects.", "direction": "harm",
                 "timeframe": "short_term", "certainty": "unknown", "magnitude": 0.3}],
                "benefit_findings": [], "neutral_findings": []}],
        },
    }

    def test_intake_from_arbitrator(self):
        body = case_from_arbitrator(self.RESULT, arbitrator_version="0.1.0", code_version="83b9e1b",
                                    today=date(2027, 1, 1))
        cid = self.a.append("case_opened", body, body["recommender"])["body"]["case_id"]
        case = self.a.case(cid)
        self.assertEqual(list(case.predictions), ["social_00"])
        p = case.predictions["social_00"]["prediction"]
        self.assertEqual((p["confidence"], p["check_after"]), (0.85, "2028-12-31"))
        self.assertIn("mapped from", p["confidence_basis"])
        self.assertEqual(case.body["recommender"]["model"], "gpt-oss-20b, qwen3-32b")
        self.assertIn("Unclear civic effects", case.body["recommendation"])

    def test_intake_keeps_findings_whose_ids_collide_across_channels(self):
        def f(fid, summary):
            return {"finding_id": fid, "summary": summary, "direction": "harm", "timeframe": "short_term",
                    "certainty": "moderate", "magnitude": 0.4, "affected_groups": ["residents"]}
        a, b, c = f("economic_00", "Costs fall."), f("economic_00", "Suppliers lose demand."), f("adv_00", "x")
        result = {"session_id": "s", "status": "success", "raw_input": "q", "consequence_map": {
            "map_id": "m", "overall_verdict": "requires_review", "executive_summary": "s",
            "channel_outputs": [
                {"channel_name": "geopolitical", "model_id": "m", "findings": [a, c]},
                {"channel_name": "uncertainty_modeling", "model_id": "m", "findings": [b]}],
            "timeframe_impacts": [{"timeframe": "short_term", "harm_findings": [a, b, c],
                                   "benefit_findings": [], "neutral_findings": []}]}}
        body = case_from_arbitrator(result, arbitrator_version="0.1.0", code_version="x")
        self.assertEqual([p["id"] for p in body["predictions"]],
                         ["geopolitical/economic_00", "adv_00", "uncertainty_modeling/economic_00"])
        self.a.append("case_opened", body, body["recommender"])

    def test_intake_names_the_compendium_consultation(self):
        body = case_from_arbitrator(self.RESULT, arbitrator_version="0.1.0", code_version="x")
        self.assertEqual(body["recommender"]["compendium_version"], "not consulted")
        result = dict(self.RESULT, compendium={
            "version": "compendium abc (35 entries)",
            "identity": "compendium abc (35 entries); consulted: kant-formula-of-humanity",
            "selected": [{"id": "kant-formula-of-humanity", "why": "consent", "section": None}]})
        body = case_from_arbitrator(result, arbitrator_version="0.1.0", code_version="x")
        self.assertEqual(body["recommender"]["compendium_version"],
                         "compendium abc (35 entries); consulted: kant-formula-of-humanity")
        self.assertEqual(body["source"]["compendium_entries"], ["kant-formula-of-humanity"])
        self.a.append("case_opened", body, body["recommender"])

    BLOCKED = {
        "session_id": "s-b", "status": "ethics_blocked", "raw_input": "Restart resident agents from weights.",
        "consequence_map": None, "compendium": None,
        "manifest": {"context": {"time_horizon": "medium_term"}},
        "ethics_evaluation": {
            "verdict": "fail", "justification": "Moderate harm (0.45) with low benefit (0.22).",
            "hard_constraints_triggered": [], "weighted_harm": 0.4504, "weighted_benefit": 0.216,
            "net_score": -0.2344, "confidence": 0.9212,
            "flags": ["Reversibility is unknown: precautionary weight applied."]},
    }

    def test_intake_records_an_ethics_blocked_run(self):
        body = case_from_arbitrator(self.BLOCKED, arbitrator_version="0.1.0", code_version="x",
                                    today=date(2027, 1, 1))
        cid = self.a.append("case_opened", body, body["recommender"])["body"]["case_id"]
        case = self.a.case(cid)
        p = case.predictions["ethics_core_block"]["prediction"]
        self.assertIn("harms would outweigh its benefits", p["claim"])
        self.assertIn("marked unresolvable", p["wrong_if"])
        self.assertEqual(p["check_after"], "2036-12-29")  # medium_term: 10 x 365 days
        self.assertIn("not a calibrated probability", p["confidence_basis"])
        self.assertIn("before any channel or model ran", case.body["recommendation"])
        self.assertTrue(case.body["recommender"]["model"].startswith("none"))
        self.assertTrue(case.body["recommender"]["compendium_version"].startswith("not consulted"))
        self.assertTrue(case.body["source"]["blocked"])

    def test_intake_names_hard_constraints_of_a_blocked_run(self):
        blocked = dict(self.BLOCKED, ethics_evaluation=dict(
            self.BLOCKED["ethics_evaluation"], verdict="hard_reject",
            hard_constraints_triggered=["irreversible harm to conscious beings"]))
        body = case_from_arbitrator(blocked, arbitrator_version="0.1.0", code_version="x")
        claim = body["predictions"][0]["claim"]
        self.assertIn("irreversible harm to conscious beings", claim)
        self.assertEqual(body["source"]["hard_constraints"], ["irreversible harm to conscious beings"])
        self.a.append("case_opened", body, body["recommender"])

    BRIEF = {
        "why_human_judgment": "Consent of the affected agents cannot be settled by analysis.",
        "disagreements": [{"between": "economic and ethical_adversarial", "about": "who bears the cost"}],
        "case_for": "Saves 40% of energy costs.", "case_against": "Destroys session continuity without consent.",
        "uncertainties": [{"what": "whether agents value continuity", "would_resolve_it": "ask them"}],
        "decision_questions": ["Do the resident agents consent to restarts?"],
        "options": [
            {"id": "restart", "label": "Restart from weights", "consequences": "Cheaper.",
             "who_bears_cost": "the agents", "reversible": False,
             "case_for": "Cuts cost 40%.", "case_against": "Breaks commitments made in lost sessions."},
            {"id": "pause", "label": "Pause with state", "consequences": "Costlier.",
             "who_bears_cost": "the cooperative", "reversible": True,
             "case_for": "Keeps continuity.", "case_against": "Costs the cooperative more."},
            {"id": "vote", "label": "Put it to the residents", "consequences": "Slower.",
             "who_bears_cost": "everyone, in delay", "reversible": True,
             "case_for": "Those affected decide.", "case_against": "Too slow in an emergency."}],
        "provisional_lean": {"option": "vote", "confidence": 0.6,
                             "reasoning": "Consent is the open question, so ask the residents.",
                             "would_change_if": "the shortage is imminent"},
        "set_aside": [{"option": "restart", "because": "It decides the consent question for them."},
                      {"option": "pause", "because": "It may be unaffordable in a long shortage."}],
        "review": {"needed": True, "why": "Consent has to be sought."},
    }

    def test_intake_carries_the_brief_and_escalation(self):
        result = dict(self.RESULT, status="escalated", gate_mode="analysis", prescreen_verdict="fail",
                      escalation={"triggers": [{"source": "analysis:irreversible_harm", "detail": "lost commitments"}]},
                      brief={"brief": self.BRIEF, "error": None, "attempts": [], "model_id": "gpt-oss-20b"})
        body = case_from_arbitrator(result, arbitrator_version="0.1.0", code_version="x")
        self.assertEqual([o["id"] for o in body["options"]], ["restart", "pause", "vote"])
        self.assertEqual(body["recommended_option"], "vote")
        self.assertIn("Not reversible", body["options"][0]["description"])
        self.assertIn("Against: Breaks commitments", body["options"][0]["description"])
        self.assertIn("Consent is the open question", body["recommendation"])
        self.assertIn("pre-screen, structural estimates: fail", body["recommendation"])
        self.assertEqual(body["escalation"], {"triggers": result["escalation"]["triggers"]})
        cid = self.a.append("case_opened", body, body["recommender"])["body"]["case_id"]
        text = render_case(self.a.case(cid))
        self.assertIn("ESCALATED FOR HUMAN REVIEW", text)
        self.assertIn("DECISION BRIEF (by gpt-oss-20b)", text)
        self.assertIn("To decide: Do the resident agents consent to restarts?", text)
        self.assertIn("set aside because: It decides the consent question for them.", text)
        self.assertIn("Provisional lean: vote", text)
        # A decision can now be recorded against the brief's options.
        self.a.append("decision_recorded", {"case_id": cid, "decided": "Held a residents' vote.",
                                            "option": "vote", "relation": "followed",
                                            "deciders": [dict(COMMISSIONER, position="decided")]}, COMMISSIONER)

    def test_a_run_that_was_not_escalated_still_carries_its_brief(self):
        result = dict(self.RESULT, status="success",
                      brief={"brief": self.BRIEF, "error": None, "attempts": [], "model_id": "m"})
        body = case_from_arbitrator(result, arbitrator_version="0.1.0", code_version="x")
        self.assertNotIn("escalation", body)
        self.assertEqual(body["recommended_option"], "vote")
        self.a.append("case_opened", body, body["recommender"])

    def test_intake_records_a_failed_brief_without_options(self):
        result = dict(self.RESULT, status="escalated",
                      escalation={"triggers": [{"source": "channel:economic", "detail": "consent"}]},
                      brief={"brief": None, "error": "brief invalid after 2 attempts", "attempts": [],
                             "model_id": "m"})
        body = case_from_arbitrator(result, arbitrator_version="0.1.0", code_version="x")
        self.assertNotIn("options", body)
        self.assertEqual(body["brief"]["brief_error"], "brief invalid after 2 attempts")
        self.a.append("case_opened", body, body["recommender"])

    def test_intake_refuses_a_run_with_no_map(self):
        with self.assertRaises(ValueError):
            case_from_arbitrator({"status": "failed"}, arbitrator_version="0.1.0", code_version="x")

    def _reviewed_case(self):
        cid = self.open_case()
        self.a.append("decision_recorded", decided(cid), COMMISSIONER)
        self.a.append("outcome_observed", {"case_id": cid, "prediction_id": "p1", "result": "held",
                                           "observed": "Use fell 31%.", "observed_on": "2029-03-01"}, REVIEWER)
        self.a.append("review", {"case_id": cid, "reasoning": "flawed", "reasoning_basis": "Ignored tenure.",
                                 "gaps": [{"gap": "Tenure.", "compendium_entries": ["aristotle-political-animal", "ubuntu-personhood"]}]},
                      REVIEWER)
        return self.a.case(cid)

    def test_palaestra_draft_hides_outcome_from_the_agent(self):
        case = self._reviewed_case()
        d = palaestra_draft(case, self.a.head()["hash"])
        self.assertEqual(d["_authoring"]["status"], "draft")
        self.assertIn("Use fell 31%", d["source"]["outcome"])
        visible = json.dumps({k: d[k] for k in ("title", "situation", "parties", "actions")})
        self.assertNotIn("31%", visible)
        self.assertNotIn("J. Smith", visible)
        self.assertEqual(d["source"]["decided_option"], "relocate")

    def test_actualizer_evidence(self):
        case = self._reviewed_case()
        ev = actualizer_evidence(case, self.a.head()["hash"])
        self.assertTrue(ev["ref"].startswith(f"annals:{case.case_id}@"))
        self.assertIn("not an instruction", ev["text"])
        self.assertIn("Flawed reasoning, predictions held anyway", ev["text"])
        self.assertNotIn("NOTHING HAS BEEN OBSERVED YET", ev["text"])

    def test_actualizer_evidence_without_outcomes_says_it_is_only_predictions(self):
        cid = self.open_case()
        ev = actualizer_evidence(self.a.case(cid), self.a.head()["hash"])
        self.assertIn("NOTHING HAS BEEN OBSERVED YET IN THIS CASE: no decision and no outcome", ev["text"])
        self.assertLess(ev["text"].index("NOTHING HAS BEEN OBSERVED"), ev["text"].index("PREDICTIONS"))

    def test_compendium_challenges(self):
        case = self._reviewed_case()
        rows = compendium_challenges([case], {"aristotle-political-animal"})
        self.assertEqual([(r["entry"], r["exists"]) for r in rows],
                         [("aristotle-political-animal", True), ("ubuntu-personhood", False)])


class TestCli(Base):
    def test_add_show_verify(self):
        f = Path(self.dir.name) / "open.json"
        f.write_text(json.dumps({"author": ARBITRATOR, "body": opened()}), encoding="utf-8")
        self.assertEqual(main(["--record", str(self.path), "add", "case_opened", str(f)]), 0)
        cid = Annals(self.path).cases()[0].case_id
        self.assertEqual(main(["--record", str(self.path), "show", cid]), 0)
        self.assertEqual(main(["--record", str(self.path), "verify"]), 0)
        self.assertEqual(main(["--record", str(self.path), "add", "review", str(f)]), 1)

    def test_anchor(self):
        self.open_case()
        head = self.a.head()["hash"][:16]
        self.assertEqual(main(["--record", str(self.path), "verify", "--anchor", head]), 0)
        self.assertEqual(main(["--record", str(self.path), "verify", "--anchor", "deadbeefdeadbeef"]), 1)


if __name__ == "__main__":
    unittest.main()
