"""Evidence-boundary checks using isolated temporary JSON fixtures, no DB service."""

import json
import tempfile
import unittest
from pathlib import Path

from virtual_player.observers.aggregator import ParameterAggregator
from virtual_player.observers.exporter import DesignDBExporter, DomainGroup


class TestExporterEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="exporter-evidence-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exporter = DesignDBExporter(
            project="EvidenceFixture", genre="Puzzle", db_root=self.root,
            domain_groups=[DomainGroup(
                "ingame", "fixture_rules", "Rules", "core", ["P1", "P2"], [], [],
            )],
        )

    def export(self, parameters):
        self.exporter.export(parameters)
        return json.loads((self.root / "base/puzzle/ingame/files/fixture_rules.json").read_text(encoding="utf-8"))

    def test_preserves_existing_fields_and_supplied_evidence(self):
        parameter = {
            "name": "tap_limit", "value": 7, "confidence": 0.75,
            "raw_confidence": 0.9, "status": "observed",
            "sources": [{"observer": 2, "weight": 0.75, "notes": "OCR screen 4"}],
            "context": {"build": "fixture-1", "device": "fixture-phone"},
            "evidence_refs": [{"path": "screen4.png", "sha256": "fixture-hash"}],
        }
        detail = self.export({"P1": parameter})
        self.assertEqual(detail["content"]["parameters"]["P1"], parameter)
        self.assertEqual(detail["source"], "observed")
        self.assertEqual(detail["score"], 0.4)

    def test_not_observed_and_invalid_are_not_promoted(self):
        aggregated = ParameterAggregator(param_names={"P1": "missing", "P2": "invalid"}).aggregate({"P2": [None]})
        detail = self.export(aggregated)
        parameters = detail["content"]["parameters"]
        self.assertEqual(parameters["P1"]["status"], "not_observed")
        self.assertEqual(parameters["P2"]["status"], "invalid_observations")
        for parameter in parameters.values():
            self.assertIsNone(parameter["value"])
            self.assertEqual(parameter["confidence"], 0.0)
            self.assertEqual(parameter["sources"], [])

    def test_missing_status_is_unknown_and_context_is_not_fabricated(self):
        parameter = self.export({"P1": {"name": "legacy", "value": 4, "confidence": 0.8}})["content"]["parameters"]["P1"]
        self.assertEqual(parameter["status"], "unknown")
        self.assertEqual(parameter["sources"], [])
        self.assertNotIn("context", parameter)
        self.assertNotIn("evidence_refs", parameter)

    def test_disagreeing_observers_remain_weighted_selection_not_consensus(self):
        aggregator = ParameterAggregator(param_names={"P1": "limit"})
        aggregated = aggregator.aggregate({"P1": [
            {"observer": 1, "value": 7, "confidence": 0.9, "notes": "first screen"},
            {"observer": 2, "value": 9, "confidence": 0.7, "notes": "different screen"},
        ]})
        detail = self.export(aggregated)
        parameter = detail["content"]["parameters"]["P1"]
        self.assertEqual(parameter["value"], 7)
        self.assertEqual(parameter["sources"], aggregated["P1"]["sources"])
        for key in ("consensus", "reproduction", "causal_effect"):
            self.assertEqual(detail["evidence_interpretation"][key], "not_established_by_export")
        self.assertNotIn("~85-89%", json.dumps(detail))

    def test_proposed_value_keeps_its_kind_under_observed_import_route(self):
        detail = self.export({"P1": {
            "value": 5, "confidence": 0, "status": "untested", "source": "proposed",
            "evidence_kind": "design_proposal", "observation_ids": ["baseline-1"],
        }})
        parameter = detail["content"]["parameters"]["P1"]
        self.assertEqual(detail["source"], "observed")
        self.assertEqual(parameter["source"], "proposed")
        self.assertEqual(parameter["status"], "untested")
        self.assertEqual(parameter["evidence_kind"], "design_proposal")


if __name__ == "__main__":
    unittest.main()
