"""
ParameterAggregator -- Domain-Weighted Consensus Merge
=======================================================
Merges observations from multiple observers using domain-weighted confidence.

Extracted from carmatch_tester.py and made configurable.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ParameterAggregator:
    """Domain-weighted consensus merge of parameter observations."""

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
        Merge all observations into consensus values.

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

        # Collect all param IDs from observations and param_names
        all_params = set(observations.keys()) | set(self.param_names.keys())

        for param_id in sorted(all_params):
            obs_list = observations.get(param_id, [])

            # Skip internal/metadata keys
            if param_id.startswith("_"):
                continue

            name = self.param_names.get(param_id, param_id)
            domain = self.param_domains.get(param_id, "")

            if not obs_list:
                result[param_id] = {
                    "name": name,
                    "value": None,
                    "confidence": 0.0,
                    "raw_confidence": 0.0,
                    "sources": [],
                    "status": "not_observed",
                }
                continue

            # Filter valid observations
            valid = [o for o in obs_list if isinstance(o, dict) and "value" in o]
            if not valid:
                result[param_id] = {
                    "name": name,
                    "value": None,
                    "confidence": 0.0,
                    "raw_confidence": 0.0,
                    "sources": [],
                    "status": "invalid_observations",
                }
                continue

            # Weight each observation
            weighted = []
            for obs in valid:
                obs_id = obs.get("observer", 0)
                raw_conf = obs.get("confidence", 0.5)

                # Apply domain weight
                obs_domains = self.domain_weights.get(obs_id, {})
                domain_weight = obs_domains.get(domain, 0.5) if domain else 0.5
                weight = round(raw_conf * domain_weight, 3)

                weighted.append({
                    "obs": obs,
                    "weight": weight,
                    "observer": obs_id,
                })

            # Sort by weight descending
            weighted.sort(key=lambda w: w["weight"], reverse=True)

            # Pick best observation
            best = weighted[0]
            sources = [
                {
                    "observer": w["observer"],
                    "weight": w["weight"],
                    "notes": w["obs"].get("notes", ""),
                }
                for w in weighted[:3]  # Top 3 sources
            ]

            result[param_id] = {
                "name": name,
                "value": best["obs"]["value"],
                "confidence": best["weight"],
                "raw_confidence": best["obs"].get("confidence", 0.5),
                "sources": sources,
                "status": "observed",
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
