"""
Phase 0 of .Documentation/reconcile-architecture-plan.md, beyond the flyer's
governance contract (ai.tests.test_governance_contract):

- every canonical document's reference spec is well-formed, and is
  reachable: the deterministic core, given ideal semantic input, satisfies it
  (a spec no correct pipeline could pass would make the Phase 5 gate
  meaningless);
- segment ids and texts of the canonical documents are pinned: provenance
  (EvidenceReference.locator), replay fixtures and the planned cell ids all
  rest on them, so any change to segmentation must be deliberate
  (ONYXJAR_UPDATE_SEGMENT_PINS=1 regenerates the pins);
- a raw trace becomes a replay fixture deterministically
  (`manage.py capture_reconcile_fixture`).
"""

import json
import os
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.tracing import KEYED_STAGES, capture_fixture, fixture_step, request_of
from ai.tests.reference import REFERENCES, assert_reference, load_spec, run_core
from ai.tests.rugby import FLYER_ASSETS, INTENT as RUGBY_INTENT, RugbyFixture
from ai.tests.support import assertion, entity, frame, target
from ai.tests.test_evidence_lifecycle import flyer_assets
from ai.tests.test_governance_contract import INTENT as FLYER_INTENT, GovernanceContractTestCase, cite, ent, rel
from ai.tests.test_reconcile_resilience import ASSETS as DEPTH_ASSETS, INTENT as DEPTH_INTENT, LAYERS, DepthFixture

FIXTURES = Path(__file__).parent / "fixtures"
SEGMENT_PINS = FIXTURES / "segments"
REPORT_TEXT = (FIXTURES / "international_rugby_report.txt").read_text(encoding="utf-8")
REPORT_ASSETS = [{"name": "international_rugby_report.txt", "content": REPORT_TEXT, "mime_type": "text/plain"}]

SPEC_KEYS = {"document", "description", "required_objects", "required_relationships", "required_blocked",
             "forbidden_objects", "forbidden_relationships"}
STATES = {"undecidable", "insufficient_evidence", "not_stated"}


class SpecShapeTests(SimpleTestCase):

    def test_every_spec_is_well_formed(self):
        specs = sorted(REFERENCES.glob("*.json"))
        self.assertEqual({p.stem for p in specs}, {"international_flyer", "international_report", "rugby_flyer", "depth_chain"})
        for path in specs:
            spec = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(spec=path.stem):
                self.assertEqual(set(spec), SPEC_KEYS)
                ids = [item["id"] for key in SPEC_KEYS - {"document", "description"} for item in spec[key]]
                self.assertEqual(len(ids), len(set(ids)), "assertion ids are unique")
                for item in spec["required_blocked"]:
                    self.assertTrue(set(item["states"]) <= STATES, item)
                for item in [*spec["required_objects"], *spec["required_relationships"]]:
                    self.assertTrue(item.get("names") or (item.get("subject") and item.get("object")), item)


# -- the specs are reachable ----------------------------------------------------------


class InternationalReportSpecTests(GovernanceContractTestCase):
    """The prose-only report: the same ontology and intent as the flyer."""

    def setUp(self):
        super().setUp()
        self.assets = REPORT_ASSETS

    def ideal_report_items(self):
        name = "Pacific International Rugby Championship 2027"
        teams = [("NZ", "New Zealand"), ("FJ", "Fiji"), ("JP", "Japan"), ("WS", "Samoa"), ("AU", "Australia"),
                 ("AR", "Argentina"), ("ZA", "South Africa"), ("TO", "Tonga")]
        s = self.text
        items = [ent("T", name, "tournament", "S1#2")]
        items += [ent(eid, team, "team", "S1#2") for eid, team in teams]
        items += [rel(f"HT2_{eid}", "T", "brought together", eid, "has_team_2", [cite("S1#2", s("S1#2"))]) for eid, _ in teams]
        items += [ent("PA", "Pool A", "stage", "S1#3"), ent("PB", "Pool B", "stage", "S1#3"), ent("QF", "quarter-finals", "stage", "S1#9")]
        items += [rel(f"HS_{eid}", "T", "opened with", eid, "has_stage", [cite("S1#3", s("S1#3"))]) for eid in ("PA", "PB")]
        items.append(rel("HS_QF", "T", "quarter-finals", "QF", "has_stage", [cite("S1#9", s("S1#9"))]))
        venues = [("V1", "Eden Park", "S1#4"), ("V2", "Sky Stadium", "S1#5"), ("V3", "Forsyth Barr Stadium", "S1#6"),
                  ("V4", "FMG Stadium Waikato", "S1#7"), ("V5", "McLean Park", "S1#8"), ("V6", "Orangetheory Stadium", "S1#9")]
        items += [ent(eid, venue, "venue", seg) for eid, venue, seg in venues]
        matches = [("M1", "New Zealand v Fiji", "PA", "V1", ("NZ", "FJ"), "S1#4"), ("M2", "Japan v Samoa", "PA", "V2", ("JP", "WS"), "S1#5"),
                   ("M3", "Australia v Argentina", "PB", "V3", ("AU", "AR"), "S1#6"),
                   ("M4", "South Africa v Tonga", "PB", "V4", ("ZA", "TO"), "S1#7"),
                   ("Q1", "Pool A winner v Pool B runner-up", "QF", "V6", (), "S1#9")]
        for eid, match, stage, venue, sides, seg in matches:
            sentence = [cite(seg, s(seg))]
            items += [ent(eid, match, "match", seg), rel(f"HM_{eid}", stage, "includes", eid, "has_match", sentence),
                      rel(f"PL_{eid}", eid, "played at", venue, "played_at", sentence)]
            items += [rel(f"HT_{eid}_{team}", eid, "between", team, "has_team", sentence) for team in sides]
        return items

    def test_ideal_input_satisfies_the_report_spec(self):
        core = run_core(self, model=self.model, frame=self.frame(), items=self.ideal_report_items(), assets=self.assets, intent=FLYER_INTENT)

        assert_reference(self, core.outcome, load_spec("international_report"))


class RugbyFlyerSpecTests(RugbyFixture):

    def test_ideal_input_satisfies_the_rugby_flyer_spec(self):
        core = run_core(self, model=self.model, frame=self.flyer_frame(), items=self.flyer_items(), assets=FLYER_ASSETS, intent=RUGBY_INTENT)

        assert_reference(self, core.outcome, load_spec("rugby_flyer"))


class DepthChainSpecTests(DepthFixture):

    def test_ideal_input_satisfies_the_depth_chain_spec(self):
        kinds = {"North Depot": "site", **{name: kind for _, _, name, kind, _ in LAYERS}}
        ids = {name: f"E{n}" for n, name in enumerate(kinds, 1)}
        items = [entity(ids[name], name, kind, hint=kind, excerpt=name) for name, kind in kinds.items()]
        keys = ("located_in", "part_of", "member_of", "governed_by")
        items += [assertion(f"A{n}", ids[subject], predicate, ids[obj], hint=key, excerpt=sentence)
                  for n, ((subject, predicate, obj, _, sentence), key) in enumerate(zip(LAYERS, keys), 1)]
        core = run_core(self, model=self.model, frame=frame([target("T1", "sites", "sites", hint="site")]), items=items,
                        assets=DEPTH_ASSETS, intent=DEPTH_INTENT)

        assert_reference(self, core.outcome, load_spec("depth_chain"))


# -- segment ids are pinned --------------------------------------------------------------


def _segments(assets) -> list[list[str]]:
    return [[s.segment_id, s.kind, s.text] for s in EvidenceBundle.from_assets(assets).segments()]


CANONICAL_DOCUMENTS = {
    "international_flyer": flyer_assets,
    "rugby_flyer": lambda: FLYER_ASSETS,
    "international_report": lambda: REPORT_ASSETS,
}


class SegmentIdStabilityTests(SimpleTestCase):

    def test_canonical_documents_segment_exactly_as_pinned(self):
        for name, assets in CANONICAL_DOCUMENTS.items():
            pin = SEGMENT_PINS / f"{name}.json"
            observed = _segments(assets())
            if os.getenv("ONYXJAR_UPDATE_SEGMENT_PINS") == "1":
                SEGMENT_PINS.mkdir(exist_ok=True)
                pin.write_text(json.dumps(observed, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                continue
            with self.subTest(document=name):
                self.assertTrue(pin.exists(), f"No segment pin for {name}: run with ONYXJAR_UPDATE_SEGMENT_PINS=1.")
                self.assertEqual(observed, json.loads(pin.read_text(encoding="utf-8")))


# -- raw trace -> replay fixture --------------------------------------------------------


class CaptureFixtureTests(SimpleTestCase):

    def raw_trace(self, directory):
        steps = [
            {"kind": "provider", "run_id": "r", "sequence": 1, "stage": "extraction", "attempt": 1, "decision": "advance",
             "schema": "ExtractionResult", "payload": {"stage": "extraction", "segments": []}, "output": {"evidence": {}},
             "issues": [], "provider": "openai", "provider_model": "m", "usage": {"total_tokens": 5}, "payload_chars": 9},
            {"kind": "deterministic", "run_id": "r", "sequence": 2, "stage": "analysis", "decision": "advance", "next": "gap_probe",
             "snapshot": {"ledger": []}},
            {"kind": "provider", "run_id": "r", "sequence": 3, "stage": "gap_probe", "attempt": 1, "decision": "advance",
             "schema": "ProbeResult", "payload": {"stage": "gap_probe", "requirements": [{"requirement_id": "req:E1:x:subject"}]},
             "output": {"verdicts": []}, "provider_model": "m", "started_at": "t0"},
        ]
        for step in steps:
            (Path(directory) / f"{step['sequence']:03d}-{step['stage']}.json").write_text(json.dumps(step), encoding="utf-8")

    def test_a_raw_trace_becomes_a_stripped_fixture_with_its_requests(self):
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as out:
            self.raw_trace(raw)
            call_command("capture_reconcile_fixture", raw, out, stdout=open(os.devnull, "w"))
            written = sorted(p.name for p in Path(out).glob("*.json"))
            extraction = json.loads((Path(out) / "001-extraction.json").read_text(encoding="utf-8"))
            probe = json.loads((Path(out) / "003-gap_probe.json").read_text(encoding="utf-8"))

        self.assertEqual(written, ["001-extraction.json", "003-gap_probe.json"])
        self.assertEqual(list(extraction), ["kind", "run_id", "sequence", "stage", "attempt", "decision", "schema", "output", "provider_model"])
        self.assertEqual(probe["request"], {"requirements": ["req:E1:x:subject"]})
        self.assertNotIn("payload", probe)
        self.assertNotIn("started_at", probe)

    def test_captured_fixtures_carry_the_request_replay_keys_on(self):
        # Every keyed step of a fixture replayed by work (the equivalence
        # runs) has a request, in the shape request_of produces. (Older
        # fixtures replayed strictly in captured order carry none.)
        from ai.tests.test_trace_equivalence import RUNS

        for path in sorted(p for run in RUNS for p in (FIXTURES / "traces" / f"international_flyer_{run}").glob("*.json")):
            step = json.loads(path.read_text(encoding="utf-8"))
            if step["stage"] in KEYED_STAGES:
                with self.subTest(step=f"{path.parent.name}/{path.name}"):
                    self.assertIsInstance(step.get("request"), dict)

    def test_capture_is_idempotent_on_its_own_output(self):
        fixture = {"kind": "provider", "run_id": "r", "sequence": 7, "stage": "adjudication", "attempt": 1, "decision": "advance",
                   "schema": "AdjudicationResult", "output": {"answers": []}, "provider_model": "m"}
        raw = {**fixture, "payload": {"stage": "adjudication", "questions": [{"question_id": "q1"}]}}

        self.assertEqual(fixture_step(raw), {**fixture, "request": {"questions": ["q1"]}})
        self.assertEqual(request_of("adjudication", raw["payload"]), {"questions": ["q1"]})
        with tempfile.TemporaryDirectory() as raw_dir, tempfile.TemporaryDirectory() as out:
            (Path(raw_dir) / "007-adjudication.json").write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(len(capture_fixture(raw_dir, out)), 1)
