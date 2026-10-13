"""
ParameterAggregator -- Domain-Weighted Selection with Observation Provenance
=======================================================
Merges observations from multiple observers using domain-weighted confidence.

Extracted from carmatch_tester.py and made configurable.
"""

import logging
import hashlib
import json
import math
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _canonical(value: Any) -> str:
    """Canonical JSON for content identity; never coerce/drop unsupported values."""
    def check(item):
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if isinstance(item, list):
            for child in item:
                check(child)
            return
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError('Observation provenance requires finite JSON values and string object keys')
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class ParameterAggregator:
    """Select the highest weighted value; retain all evidence without claiming consensus."""

    def __init__(
        self,
        param_names: Optional[Dict[str, str]] = None,
        param_domains: Optional[Dict[str, str]] = None,
        domain_weights: Optional[Dict[int, Dict[str, float]]] = None,
    ):
        """
        Args:
            param_names: {param_id: human_readable_name}. e.g. {"CM01": "board_width_cells"}
            param_domains: {param_id: domain}. e.g. {"CM01": "ingame"}
            domain_weights: {observer_id: {domain: weight}}.
                            e.g. {1: {"gameplay": 1.0, "content": 0.8}}
        """
        self.param_names = param_names or {}
        self.param_domains = param_domains or {}
        self.domain_weights = domain_weights or {}

    def aggregate(
        self,
        observations: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Select weighted values and retain every supplied observation, including dissent.

        Args:
            observations: {param_id: [observation_dict, ...]}

        Returns:
            {param_id: {
                "name": str,
                "value": Any,
                "confidence": float,
                "raw_confidence": float,
                "sources": [{"observer": int, "weight": float, "notes": str}, ...]
            }}
        """
        result = {}
        if not isinstance(observations, dict) or any(not isinstance(key, str) for key in observations):
            raise ValueError('Observations must map string parameter IDs to lists')

        # Collect all param IDs from observations and param_names
        all_params = set(observations.keys()) | set(self.param_names.keys())

        for param_id in sorted(all_params):
            obs_list = observations.get(param_id, [])

            # Skip internal/metadata keys
            if param_id.startswith("_"):
                continue
            if not isinstance(obs_list, list):
                raise ValueError(f'{param_id}: observations must be a list')

            name = self.param_names.get(param_id, param_id)
            domain = self.param_domains.get(param_id, "")

            records = []
            occurrences = {}
            supplied_ids = {}
            weighted = []
            for raw in obs_list:
                obs = deepcopy(raw)
                canonical = _canonical(obs)
                digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
                scoped = hashlib.sha256(_canonical([param_id, obs]).encode('utf-8')).hexdigest()
                occurrences[scoped] = occurrences.get(scoped, 0) + 1
                record = {
                    "id": f'obs_{scoped}_{occurrences[scoped]}',
                    "sha256": digest, "raw": obs, "eligible": False, "issues": [],
                }
                records.append(record)
                if not isinstance(obs, dict):
                    record['issues'].append('observation must be an object containing value')
                    continue
                # Supplied identities stay in raw. Generated identities are never
                # allowed to silently resolve two different payloads under one ID.
                for id_field in ('observation_id', 'id'):
                    if id_field not in obs:
                        continue
                    supplied_id = obs[id_field]
                    if not isinstance(supplied_id, str) or not supplied_id.strip():
                        record['issues'].append(f'{id_field} must be a nonempty string')
                    elif supplied_id in supplied_ids and supplied_ids[supplied_id] != digest:
                        raise ValueError(f'{param_id}: conflicting observation ID {supplied_id}')
                    else:
                        supplied_ids[supplied_id] = digest
                if "value" not in obs:
                    record['issues'].append('observation must contain value')
                obs_id = obs.get("observer", 0)
                raw_conf = obs.get("confidence", 0.5)
                if type(obs_id) not in (str, int):
                    record['issues'].append('observer must be a string or integer')
                if type(raw_conf) not in (int, float) or not 0 <= raw_conf <= 1:
                    record['issues'].append('confidence must be numeric in [0, 1]')
                if record['issues']:
                    continue
                obs_domains = self.domain_weights.get(obs_id, {})
                if not isinstance(obs_domains, dict):
                    raise ValueError(f'{param_id}: observer domain weights must be an object')
                domain_weight = obs_domains.get(domain, 0.5) if domain else 0.5
                if type(domain_weight) not in (int, float) or not math.isfinite(domain_weight) or domain_weight < 0:
                    raise ValueError(f'{param_id}: domain weight must be finite and nonnegative')
                weight = round(raw_conf * domain_weight, 3)
                record.update(eligible=True, weight=weight)
                weighted.append({
                    "obs": obs,
                    "weight": weight,
                    "observer": obs_id,
                    "record_id": record['id'],
                })

            provenance = {
                "observations": records,
                "observation_ids": [record['id'] for record in records],
                "selected_observation_id": None,
                "alternative_values": [],
                "dissenting_observation_ids": [],
                "selection_metadata": {
                    "policy": "highest_domain_weighted_confidence",
                    "tie_break": "first_in_input_order",
                    "consensus": "not_established",
                    "reproduction": "not_established",
                    "causal_effect": "not_established",
                    "identity": "sha256_canonical_json_v1; duplicate occurrence suffix scoped to parameter",
                },
            }
            if not weighted:
                result[param_id] = {
                    "name": name, "value": None, "confidence": 0.0,
                    "raw_confidence": 0.0, "sources": [],
                    "status": "invalid_observations" if obs_list else "not_observed",
                    **provenance,
                }
                continue

            # Sort by weight descending
            weighted.sort(key=lambda w: w["weight"], reverse=True)

            # Pick best observation
            best = weighted[0]
            provenance['selected_observation_id'] = best['record_id']
            groups = {}
            selected_key = _canonical(best['obs']['value'])
            for candidate in weighted:
                key = _canonical(candidate['obs']['value'])
                groups.setdefault(key, {
                    'value': deepcopy(candidate['obs']['value']), 'observation_ids': [],
                })['observation_ids'].append(candidate['record_id'])
                if key != selected_key:
                    provenance['dissenting_observation_ids'].append(candidate['record_id'])
            provenance['alternative_values'] = list(groups.values())
            sources = [
                {
                    "observer": w["observer"],
                    "weight": w["weight"],
                    "notes": deepcopy(w["obs"].get("notes", "")),
                }
                for w in weighted[:3]  # Top 3 sources
            ]

            result[param_id] = {
                "name": name,
                "value": deepcopy(best["obs"]["value"]),
                "confidence": best["weight"],
                "raw_confidence": best["obs"].get("confidence", 0.5),
                "sources": sources,
                "status": "observed",
                **provenance,
            }

        return result

    def summary(self, aggregated: Dict[str, Dict]) -> str:
        """Generate a human-readable summary of aggregated parameters."""
        lines = ["Parameter Aggregation Summary", "=" * 50]

        observed = {k: v for k, v in aggregated.items() if v.get("status") == "observed"}
        not_observed = {k: v for k, v in aggregated.items() if v.get("status") != "observed"}

        lines.append(f"\nObserved: {len(observed)} / {len(aggregated)}")

        for pid, data in sorted(observed.items()):
            conf = data.get("confidence", 0)
            val = data.get("value", "?")
            name = data.get("name", pid)
            status = "OK" if conf >= 0.5 else "LOW"
            lines.append(f"  [{status}] {pid} ({name}): {val}  (conf={conf:.2f})")

        if not_observed:
            lines.append(f"\nNot observed: {len(not_observed)}")
            for pid, data in sorted(not_observed.items()):
                lines.append(f"  [--] {pid} ({data.get('name', pid)})")

        return "\n".join(lines)
