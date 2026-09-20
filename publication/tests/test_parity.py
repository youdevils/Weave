import json
import os
from pathlib import Path

from django.test import SimpleTestCase

from .parity_cases import build_fixture

FIXTURE = Path(__file__).resolve().parent.parent / "jstests" / "fixtures" / "parity.json"


def _serialise(fixture) -> str:
    # Round-trip through JSON so tuples/sets compare the way the file will.
    return json.dumps(fixture, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class ParityFixtureTests(SimpleTestCase):
    """
    The committed golden file must equal what the Python Explorer produces now.
    The JS engine is tested against the same file, so the two stay in step.
    """

    def test_the_committed_fixture_matches_the_python_implementation(self):
        expected = _serialise(build_fixture())

        if os.environ.get("WEAVE_UPDATE_PARITY") == "1":
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(expected, encoding="utf-8")
            self.skipTest("Parity fixture regenerated.")

        self.assertTrue(FIXTURE.exists(), "Missing fixture: run with WEAVE_UPDATE_PARITY=1 to create it.")
        actual = FIXTURE.read_text(encoding="utf-8")
        self.assertEqual(
            actual == expected,
            True,
            "publication/jstests/fixtures/parity.json is stale. If the Python Explorer behaviour changed on "
            "purpose, regenerate it with WEAVE_UPDATE_PARITY=1 and update the JS engine to match.",
        )

    def test_the_fixture_exercises_the_interesting_paths(self):
        fixture = build_fixture()
        steps = [step for case in fixture["cases"] for step in case["steps"]]

        self.assertTrue(any(step["graph"]["summary"]["truncated"] for step in steps))
        self.assertTrue(any(step["graph"]["dropped"] for step in steps))
        self.assertTrue(any(step["graph"]["summary"]["hiddenByAttributeFilter"] for step in steps))
        self.assertTrue(any(step["graph"]["summary"]["hiddenByObjectType"] for step in steps))
        searches = [s for step in steps for s in step.get("search", [])]
        self.assertTrue(any(s["result"]["total"] for s in searches))
        self.assertTrue(any(s["result"]["total"] == 0 for s in searches))
