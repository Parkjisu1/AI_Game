"""Lossless observation provenance checks; all fixtures remain under the workspace."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from virtual_player.observers.aggregator import ParameterAggregator
from virtual_player.observers.exporter import DesignDBExporter, DomainGroup


class TestAggregatorProvenance(unittest.TestCase):
    def setUp(self):
        self.aggregator = ParameterAggregator(param_domains={'P1': 'ingame'}, domain_weights={1: {'ingame': 1.0}})

    def test_all_raw_observations_and_minority_values_survive_export(self):
        raw = [{'observation_id': f'capture-{i}', 'value': 7 if i < 3 else 9,
                'confidence': 0.9 - i * 0.1, 'observer': 1,
                'input': {'tap': [i, 4]}, 'environment': {'build': 'fixture', 'device': 'phone'},
                'evidence_refs': [f'screen-{i}.png']} for i in range(5)]
        result = self.aggregator.aggregate({'P1': raw})['P1']
        self.assertEqual(result['value'], 7)
        self.assertEqual(len(result['sources']), 3)
        self.assertEqual([r['raw'] for r in result['observations']], raw)
        self.assertEqual(len(result['dissenting_observation_ids']), 2)
        selected = next(r for r in result['observations'] if r['id'] == result['selected_observation_id'])
        self.assertEqual(selected['raw'], raw[0])
        self.assertEqual({g['value'] for g in result['alternative_values']}, {7, 9})
        root = Path(__file__).resolve().parents[2] / 'output'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='aggregator-fixture-', dir=root) as tmp:
            exporter = DesignDBExporter('Fixture', 'Puzzle', domain_groups=[DomainGroup(
                'ingame', 'rules', 'Rules', 'core', ['P1'], [], [])], db_root=Path(tmp))
            exporter.export({'P1': result})
            exported = json.loads((Path(tmp) / 'base/puzzle/ingame/files/rules.json').read_text(encoding='utf-8'))
            params = exported['content']['parameters']['P1']
            self.assertNotIn('without source code access', exported['design_analysis']['context'])
            self.assertNotIn('ADB', exported['design_analysis']['context'])
            for field in ('observations', 'observation_ids', 'selected_observation_id',
                          'alternative_values', 'dissenting_observation_ids', 'selection_metadata'):
                self.assertEqual(params[field], result[field])
            self.assertEqual(params['selection_metadata']['consensus'], 'not_established')
            json.dumps(exported, allow_nan=False)

    def test_identity_is_content_based_and_duplicate_occurrences_are_distinct(self):
        a = {'value': 7, 'confidence': 0.8, 'environment': {'build': 'v1'}}
        b = {'value': 9, 'confidence': 0.7}
        first = self.aggregator.aggregate({'P1': [a, b, a]})['P1']
        second = self.aggregator.aggregate({'P1': [b, a, a]})['P1']
        self.assertEqual(set(first['observation_ids']), set(second['observation_ids']))
        self.assertEqual(len(set(first['observation_ids'])), 3)
        encoded = json.dumps(a, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        self.assertEqual(first['observations'][0]['sha256'], hashlib.sha256(encoded.encode('utf-8')).hexdigest())
        reordered = {'environment': {'build': 'v1'}, 'confidence': 0.8, 'value': 7}
        self.assertEqual(self.aggregator.aggregate({'P1': [reordered]})['P1']['observation_ids'][0], first['observation_ids'][0])

    def test_deepcopy_isolates_caller_records_and_selected_value(self):
        raw = {'value': {'levels': [1, 2]}, 'confidence': 0.9, 'environment': {'build': ['v1']}}
        result = self.aggregator.aggregate({'P1': [raw]})['P1']
        raw['environment']['build'].append('mutated')
        raw['value']['levels'].append(3)
        self.assertEqual(result['observations'][0]['raw']['environment']['build'], ['v1'])
        self.assertEqual(result['value']['levels'], [1, 2])
        result['value']['levels'].append(4)
        self.assertEqual(result['observations'][0]['raw']['value']['levels'], [1, 2])

    def test_duplicate_supplied_id_with_different_payload_fails(self):
        for field in ('id', 'observation_id'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'conflicting observation ID'):
                self.aggregator.aggregate({'P1': [{field: 'same', 'value': 1}, {field: 'same', 'value': 2}]})
        with self.assertRaisesRegex(ValueError, 'conflicting observation ID'):
            self.aggregator.aggregate({'P1': [{'id': 'same', 'notes': 'invalid'}, {'id': 'same', 'value': 2}]})

    def test_json_representable_invalid_observations_are_preserved_but_not_selected(self):
        raw = [None, {'notes': 'missing'}, {'value': 10, 'confidence': 'high'},
               {'value': 11, 'confidence': True}, {'value': 12, 'observer': []},
               {'value': 13, 'confidence': -0.2}, {'value': 7, 'confidence': 0.6}]
        result = self.aggregator.aggregate({'P1': raw})['P1']
        self.assertEqual([r['raw'] for r in result['observations']], raw)
        self.assertEqual(result['value'], 7)
        self.assertTrue(all(r['issues'] and not r['eligible'] for r in result['observations'][:-1]))
        empty = self.aggregator.aggregate({'P1': raw[:-1]})['P1']
        self.assertEqual(empty['status'], 'invalid_observations')
        self.assertIsNone(empty['selected_observation_id'])

    def test_nonfinite_or_nonjson_values_fail_instead_of_losing_provenance(self):
        for value in (float('nan'), float('inf'), -float('inf'), object(), (1, 2), {1: 'key'}):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                self.aggregator.aggregate({'P1': [{'value': value}]})
        with self.assertRaises(ValueError):
            self.aggregator.aggregate({'P1': [{'value': 7, 'confidence': float('nan')}]})
        with self.assertRaisesRegex(ValueError, 'must be a list'):
            self.aggregator.aggregate({'P1': {'value': 7}})

    def test_weighting_and_input_order_tie_policy_are_unchanged(self):
        raw = [{'value': 7, 'observer': 2, 'confidence': 0.9},
               {'value': 8, 'observer': 1, 'confidence': 0.6},
               {'value': 9, 'observer': 1, 'confidence': 0.6}]
        result = self.aggregator.aggregate({'P1': raw})['P1']
        self.assertEqual(result['value'], 8)
        self.assertEqual(result['confidence'], 0.6)
        self.assertEqual(result['raw_confidence'], 0.6)
        for field in ('consensus', 'reproduction', 'causal_effect'):
            self.assertEqual(result['selection_metadata'][field], 'not_established')
        self.aggregator.domain_weights[1]['ingame'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'domain weight'):
            self.aggregator.aggregate({'P1': raw})

    def test_empty_parameter_has_no_fabricated_observation(self):
        result = ParameterAggregator(param_names={'P1': 'missing'}).aggregate({})['P1']
        self.assertEqual(result['status'], 'not_observed')
        self.assertEqual(result['observations'], [])
        self.assertIsNone(result['selected_observation_id'])


if __name__ == '__main__':
    unittest.main()
