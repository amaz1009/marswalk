"""EVA timeline synthesis and time budget accounting.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 6.5:
- walk_time = sum of step/leg nominal walking times across all legs (including return)
- margin_time = (traverse_time_margin - 1) * walk_time
- work_time = sum over stops of (stop.work_time_min or default_work_time_min) * 60
- total_time = walk_time + margin_time + work_time
- time_available = max_eva_hours * 3600
- reserve_required = return_reserve_fraction * time_available
- reserve_remaining = time_available - total_time
- Chronological timeline entries: WALK and WORK blocks, followed by MARGIN and RESERVE.
"""

from typing import Sequence

from app.models.enums import TimelineKind
from app.models.eva import EvaConfig, RouteLeg, RouteTotals, Stop, TimelineEntry


def compute_eva_timeline(
    legs: Sequence[RouteLeg],
    stops: Sequence[Stop],
    config: EvaConfig,
    destination_work_time_min: float = 0.0,
) -> tuple[list[TimelineEntry], RouteTotals]:
    """Compute chronological EVA timeline entries and integrated time totals.

    Args:
        legs: Ordered traverse legs (including intermediate legs and return leg).
        stops: Ordered intermediate science waypoints (0 to 8).
        config: Effective EvaConfig parameters.
        destination_work_time_min: Optional scientific work duration at primary destination.
            Default is 0.0 (no WORK entry generated if <= 0).

    Returns:
        A tuple of (timeline_entries, route_totals).
    """
    # 1. Nominal walk time and distances across all traversed legs
    walk_time_s = sum(float(leg.walk_time_s) for leg in legs)
    horizontal_dist_m = sum(float(leg.horizontal_distance_m) for leg in legs)
    surface_dist_m = sum(float(leg.surface_distance_m) for leg in legs)

    # 2. Field margin applies to walking time only (spec section 6.5)
    margin_factor = float(config.traverse_time_margin)
    margin_time_s = (margin_factor - 1.0) * walk_time_s

    # 3. Scientific work time at intermediate stops and destination
    stop_work_seconds: list[tuple[str, float]] = []
    for s in stops:
        work_min = (
            float(s.work_time_min)
            if s.work_time_min is not None
            else float(config.default_work_time_min)
        )
        stop_work_seconds.append((s.name or s.stop_id, work_min * 60.0))

    dest_work_s = max(0.0, float(destination_work_time_min) * 60.0)
    work_time_s = sum(w for _, w in stop_work_seconds) + dest_work_s

    # 4. Total mission time, available budget, and contingency reserves
    total_time_s = walk_time_s + margin_time_s + work_time_s
    time_available_s = float(config.max_eva_hours) * 3600.0
    reserve_required_s = float(config.return_reserve_fraction) * time_available_s
    reserve_remaining_s = time_available_s - total_time_s

    # 5. Build chronological timeline schedule
    entries: list[TimelineEntry] = []
    current_time_s = 0.0

    # Match stops with outbound legs: leg i goes from point i to point i+1
    # For n intermediate stops, outbound path has n+1 legs:
    #   leg 0: base -> stop 0
    #   leg 1: stop 0 -> stop 1
    #   ...
    #   leg n: stop n-1 -> destination
    #   leg n+1 (optional): destination -> base
    num_stops = len(stops)

    for idx, leg in enumerate(legs):
        leg_walk_s = float(leg.walk_time_s)
        walk_label = f"Walk: {leg.from_label} to {leg.to_label}"
        entries.append(
            TimelineEntry(
                kind=TimelineKind.WALK,
                label=walk_label,
                start_s=current_time_s,
                duration_s=leg_walk_s,
            )
        )
        current_time_s += leg_walk_s

        # If this leg arrives at an intermediate stop, add WORK entry for that stop
        if idx < num_stops:
            stop_label, stop_duration_s = stop_work_seconds[idx]
            if stop_duration_s > 0.0:
                entries.append(
                    TimelineEntry(
                        kind=TimelineKind.WORK,
                        label=f"Work: {stop_label}",
                        start_s=current_time_s,
                        duration_s=stop_duration_s,
                    )
                )
                current_time_s += stop_duration_s
        elif idx == num_stops and dest_work_s > 0.0:
            # Arrived at destination and destination has scheduled work time
            entries.append(
                TimelineEntry(
                    kind=TimelineKind.WORK,
                    label="Work: Destination",
                    start_s=current_time_s,
                    duration_s=dest_work_s,
                )
            )
            current_time_s += dest_work_s

    # Append field margin entry
    entries.append(
        TimelineEntry(
            kind=TimelineKind.MARGIN,
            label="Field traverse margin",
            start_s=current_time_s,
            duration_s=margin_time_s,
        )
    )
    current_time_s += margin_time_s

    # Append contingency reserve entry (duration clamped at 0.0 if exhausted)
    reserve_duration_s = max(0.0, reserve_remaining_s)
    entries.append(
        TimelineEntry(
            kind=TimelineKind.RESERVE,
            label="Return reserve",
            start_s=current_time_s,
            duration_s=reserve_duration_s,
        )
    )

    totals = RouteTotals(
        horizontal_distance_m=horizontal_dist_m,
        surface_distance_m=surface_dist_m,
        walk_time_s=walk_time_s,
        margin_time_s=margin_time_s,
        work_time_s=work_time_s,
        total_time_s=total_time_s,
        time_available_s=time_available_s,
        reserve_required_s=reserve_required_s,
        reserve_remaining_s=reserve_remaining_s,
    )

    return entries, totals
