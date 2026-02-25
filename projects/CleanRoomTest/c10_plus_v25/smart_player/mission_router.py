"""
Mission Router
===============
Maps mission IDs to target screens and manages visit progress.
Determines which screen to visit next based on mission requirements.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core import log
from smart_player.nav_graph import NavigationGraph
from genres import MissionPlan


class MissionProgress:
    """Tracks screenshot collection progress for a single mission."""

    def __init__(self, plan: MissionPlan):
        self.plan = plan
        self.captured: Dict[str, int] = {}  # screen_type -> count captured
        self.start_time: float = 0.0
        self.stuck_consecutive: int = 0

    def record_capture(self, screen_type: str):
        self.captured[screen_type] = self.captured.get(screen_type, 0) + 1
        self.stuck_consecutive = 0

    def record_stuck(self):
        self.stuck_consecutive += 1

    @property
    def elapsed_minutes(self) -> float:
        if self.start_time <= 0:
            return 0.0
        return (time.time() - self.start_time) / 60.0


class MissionRouter:
    """Routes missions to target screens and plans visit order."""

    STUCK_LIMIT = 5  # Consecutive stuck before mission abort

    def __init__(self, graph: NavigationGraph,
                 mission_plans: Dict[int, MissionPlan]):
        self.graph = graph
        # Auto-filter targets to only those reachable in the graph
        self.plans = self._filter_plans(mission_plans)
        self._progress: Dict[int, MissionProgress] = {}

    def _filter_plans(self, plans: Dict[int, MissionPlan]) -> Dict[int, MissionPlan]:
        """Remove targets that don't exist as non-popup nodes in the graph."""
        graph_screens = {
            n for n in self.graph.nodes
            if not n.startswith("popup_") and n not in ("unknown", "loading", "black_screen")
        }
        if not graph_screens:
            return plans

        filtered = {}
        for mid, plan in plans.items():
            valid_targets = [t for t in plan.targets if t in graph_screens]
            if not valid_targets:
                # Fallback: use whatever graph screens are available
                valid_targets = sorted(graph_screens)[:4]
            valid_screenshots = {
                t: n for t, n in plan.required_screenshots.items()
                if t in valid_targets
            }
            # Ensure all targets have at least 1 required screenshot
            for t in valid_targets:
                if t not in valid_screenshots:
                    valid_screenshots[t] = 1
            filtered[mid] = MissionPlan(
                targets=valid_targets,
                required_screenshots=valid_screenshots,
                max_time_minutes=plan.max_time_minutes,
                strategy=plan.strategy,
            )
            if set(valid_targets) != set(plan.targets):
                removed = set(plan.targets) - set(valid_targets)
                if removed:
                    log(f"  [Router] Mission {mid}: removed unreachable targets: {removed}")
        return filtered

    def start_mission(self, mission_id: int) -> Optional[MissionProgress]:
        """Initialize progress tracking for a mission."""
        plan = self.plans.get(mission_id)
        if not plan:
            log(f"  [Router] No plan for mission {mission_id}")
            return None

        progress = MissionProgress(plan)
        progress.start_time = time.time()
        self._progress[mission_id] = progress
        return progress

    def get_next_target(self, mission_id: int, current_screen: str) -> Optional[str]:
        """Determine the next screen to visit for this mission.

        Strategy-aware target selection:
        - sequential: visit targets in order
        - breadth_first: visit least-captured target
        - depth_first: stay on current target until enough screenshots
        - data_focused: prioritize targets with required_screenshots deficit
        """
        progress = self._progress.get(mission_id)
        if not progress:
            return None

        plan = progress.plan
        strategy = plan.strategy

        # Filter to targets not yet fully captured
        deficit_targets = []
        for target in plan.targets:
            required = plan.required_screenshots.get(target, 1)
            captured = progress.captured.get(target, 0)
            if captured < required:
                deficit_targets.append((target, required - captured))

        if not deficit_targets:
            return None  # All targets fulfilled

        if strategy == "sequential":
            # Visit in declared order
            return deficit_targets[0][0]

        elif strategy == "breadth_first":
            # Visit the target we've seen the least
            deficit_targets.sort(key=lambda t: progress.captured.get(t[0], 0))
            return deficit_targets[0][0]

        elif strategy == "depth_first":
            # If current screen is a target, stay there
            for target, deficit in deficit_targets:
                if target == current_screen:
                    return target
            return deficit_targets[0][0]

        elif strategy in ("data_focused", "economy_track", "combat_focused"):
            # Prioritize largest deficit
            deficit_targets.sort(key=lambda t: t[1], reverse=True)
            return deficit_targets[0][0]

        elif strategy == "visual_sweep":
            # Same as breadth_first for visual measurement
            deficit_targets.sort(key=lambda t: progress.captured.get(t[0], 0))
            return deficit_targets[0][0]

        else:
            # Default: sequential
            return deficit_targets[0][0]

    def plan_visit_order(self, mission_id: int, start_screen: str) -> List[str]:
        """Plan the optimal order to visit all mission targets.

        Uses graph distance from start_screen to sort targets for
        efficient navigation (nearest-neighbor heuristic).
        """
        plan = self.plans.get(mission_id)
        if not plan:
            return []

        targets = list(plan.targets)

        # Sort by graph distance from start_screen (greedy nearest-neighbor)
        ordered = []
        remaining = set(targets)
        current = start_screen

        while remaining:
            best_target = None
            best_dist = float("inf")
            for t in remaining:
                path = self.graph.find_path(current, t)
                dist = len(path) if path is not None else 999
                if dist < best_dist:
                    best_dist = dist
                    best_target = t
            if best_target:
                ordered.append(best_target)
                remaining.remove(best_target)
                current = best_target
            else:
                # Unreachable targets go at the end
                ordered.extend(remaining)
                break

        return ordered

    def is_mission_complete(self, mission_id: int) -> bool:
        """Check if a mission's completion conditions are met.

        Complete if ANY of:
        1. All required_screenshots fulfilled
        2. max_time_minutes exceeded
        3. Stuck STUCK_LIMIT consecutive times
        """
        progress = self._progress.get(mission_id)
        if not progress:
            return True

        plan = progress.plan

        # Condition 1: All screenshots collected
        all_done = True
        for target in plan.targets:
            required = plan.required_screenshots.get(target, 1)
            captured = progress.captured.get(target, 0)
            if captured < required:
                all_done = False
                break
        if all_done:
            log(f"  [Router] Mission {mission_id}: complete (all screenshots)")
            return True

        # Condition 2: Time exceeded
        if plan.max_time_minutes > 0 and progress.elapsed_minutes > plan.max_time_minutes:
            log(f"  [Router] Mission {mission_id}: timeout "
                f"({progress.elapsed_minutes:.1f} > {plan.max_time_minutes} min)")
            return True

        # Condition 3: Stuck
        if progress.stuck_consecutive >= self.STUCK_LIMIT:
            log(f"  [Router] Mission {mission_id}: stuck "
                f"({progress.stuck_consecutive} consecutive)")
            return True

        return False

    def get_progress_summary(self, mission_id: int) -> str:
        """Return a human-readable progress summary."""
        progress = self._progress.get(mission_id)
        if not progress:
            return "No progress"

        parts = []
        for target in progress.plan.targets:
            required = progress.plan.required_screenshots.get(target, 1)
            captured = progress.captured.get(target, 0)
            parts.append(f"{target}:{captured}/{required}")
        return ", ".join(parts)
