"""Unit tests for EVA engines (T-EVA-03, T-EVA-04, T-EVA-05).

Verifies:
- T-EVA-03: EVA timeline time budget accumulation (hand-derived literals).
- T-EVA-04: Default EVA parameters and completeness of AssumptionRecords.
- T-EVA-05: Timeline exceeding budget (clamped RESERVE entry, negative remaining in totals).
- Destination work time conditional entry generation per spec section 6.5.
- Margin applied strictly to walking time only (no double counting).
"""

import math
from pathlib import Path

import pytest

from app.engines.eva.defaults import (
    get_default_assumption_records,
    get_default_eva_config,
    get_default_eva_response,
    resolve_eva_config,
)
from app.engines.eva.timeline import compute_eva_timeline
from app.models.enums import DataClass, TimelineKind
from app.models.eva import EvaConfigOverride, RouteLeg, Stop
from app.models.geometry import GeoPoint


def test_default_eva_config_exact_literals() -> None:
    """EvaConfig values must equal exact constants specified in spec section 6.2."""
    config = get_default_eva_config()
    assert math.isclose(config.base_speed_kmh, 2.7, rel_tol=1e-9)
    assert math.isclose(config.max_slope_deg, 15.0, rel_tol=1e-9)
    assert math.isclose(config.warning_slope_deg, 10.0, rel_tol=1e-9)
    assert math.isclose(config.max_eva_hours, 6.0, rel_tol=1e-9)
    assert math.isclose(config.return_reserve_fraction, 0.25, rel_tol=1e-9)
    assert math.isclose(config.traverse_time_margin, 1.25, rel_tol=1e-9)
    assert math.isclose(config.default_work_time_min, 20.0, rel_tol=1e-9)
    assert math.isclose(config.max_distance_from_base_m, 2000.0, rel_tol=1e-9)
    assert math.isclose(config.roughness_warning_m, 0.30, rel_tol=1e-9)


def test_t_eva_04_assumption_records_completeness() -> None:
    """T-EVA-04: /eva/defaults returns an AssumptionRecord for every EvaConfig field."""
    response = get_default_eva_response()
    records = response.assumptions
    assert len(records) == 9

    record_map = {r.key: r for r in records}
    expected_keys = {
        "base_speed_kmh",
        "max_slope_deg",
        "warning_slope_deg",
        "max_eva_hours",
        "return_reserve_fraction",
        "traverse_time_margin",
        "default_work_time_min",
        "max_distance_from_base_m",
        "roughness_warning_m",
    }
    assert set(record_map.keys()) == expected_keys

    # Verify verified citation keys from spec section 6.2 and section 15
    assert record_map["base_speed_kmh"].citation == "JONES-GAITS"
    assert record_map["base_speed_kmh"].data_class == DataClass.REFERENCE

    assert record_map["max_slope_deg"].citation == "PENA2023"
    assert record_map["max_slope_deg"].data_class == DataClass.REFERENCE

    assert record_map["warning_slope_deg"].citation == "JONES1989"
    assert record_map["warning_slope_deg"].data_class == DataClass.REFERENCE

    assert record_map["max_eva_hours"].citation == "ALSJ"
    assert record_map["max_eva_hours"].data_class == DataClass.ASSUMPTION

    assert record_map["traverse_time_margin"].citation == "GILKEY2011"
    assert record_map["traverse_time_margin"].data_class == DataClass.ASSUMPTION

    assert record_map["max_distance_from_base_m"].citation == "PENA2023"
    assert record_map["max_distance_from_base_m"].data_class == DataClass.REFERENCE

    # Assumption keys without cited publications
    assert record_map["return_reserve_fraction"].citation is None
    assert record_map["return_reserve_fraction"].data_class == DataClass.ASSUMPTION

    assert record_map["default_work_time_min"].citation is None
    assert record_map["default_work_time_min"].data_class == DataClass.ASSUMPTION

    assert record_map["roughness_warning_m"].citation is None
    assert record_map["roughness_warning_m"].data_class == DataClass.ASSUMPTION


def test_t_eva_03_timeline_accumulation_hand_derived() -> None:
    """T-EVA-03: Timeline accumulation with exact hand-derived constants.

    Hand Derivation:
        Leg 1: base -> stop 1, walk_time = 1200.0 s
        Stop 1: work_time_min = 30.0 min -> 1800.0 s
        Leg 2: stop 1 -> destination, walk_time = 1800.0 s
        Total nominal walk time: 1200.0 + 1800.0 = 3000.0 s
        Margin (traverse_time_margin = 1.25): (1.25 - 1.0) * 3000.0 = 750.0 s
        Work time: 1800.0 s
        Total time: 3000.0 + 750.0 + 1800.0 = 5550.0 s
        Available budget (6.0 h): 6.0 * 3600.0 = 21600.0 s
        Required reserve (0.25): 0.25 * 21600.0 = 5400.0 s
        Remaining reserve: 21600.0 - 5550.0 = 16050.0 s
    """
    config = get_default_eva_config()
    p0 = GeoPoint(lat=-4.75, lon=137.28)
    p1 = GeoPoint(lat=-4.76, lon=137.29)
    p2 = GeoPoint(lat=-4.77, lon=137.30)

    legs = [
        RouteLeg(
            from_label="base",
            to_label="stop 1",
            path=[p0, p1],
            horizontal_distance_m=1000.0,
            surface_distance_m=1050.0,
            ascent_m=20.0,
            descent_m=5.0,
            walk_time_s=1200.0,
        ),
        RouteLeg(
            from_label="stop 1",
            to_label="destination",
            path=[p1, p2],
            horizontal_distance_m=1500.0,
            surface_distance_m=1600.0,
            ascent_m=35.0,
            descent_m=10.0,
            walk_time_s=1800.0,
        ),
    ]

    stops = [
        Stop(
            stop_id="st_1",
            name="Stop Alpha",
            point=p1,
            work_time_min=30.0,
        )
    ]

    entries, totals = compute_eva_timeline(
        legs=legs,
        stops=stops,
        config=config,
        destination_work_time_min=0.0,
    )

    # Hand-derived assertions with literal constants
    assert math.isclose(totals.walk_time_s, 3000.0, rel_tol=1e-9)
    assert math.isclose(totals.margin_time_s, 750.0, rel_tol=1e-9)
    assert math.isclose(totals.work_time_s, 1800.0, rel_tol=1e-9)
    assert math.isclose(totals.total_time_s, 5550.0, rel_tol=1e-9)
    assert math.isclose(totals.time_available_s, 21600.0, rel_tol=1e-9)
    assert math.isclose(totals.reserve_required_s, 5400.0, rel_tol=1e-9)
    assert math.isclose(totals.reserve_remaining_s, 16050.0, rel_tol=1e-9)

    # Verify no margin is double-counted in leg nominal walk times
    assert totals.walk_time_s == legs[0].walk_time_s + legs[1].walk_time_s

    # Verify chronological sequence and start/duration consistency
    assert len(entries) == 5
    assert entries[0].kind == TimelineKind.WALK
    assert math.isclose(entries[0].start_s, 0.0, rel_tol=1e-9)
    assert math.isclose(entries[0].duration_s, 1200.0, rel_tol=1e-9)

    assert entries[1].kind == TimelineKind.WORK
    assert math.isclose(entries[1].start_s, 1200.0, rel_tol=1e-9)
    assert math.isclose(entries[1].duration_s, 1800.0, rel_tol=1e-9)

    assert entries[2].kind == TimelineKind.WALK
    assert math.isclose(entries[2].start_s, 3000.0, rel_tol=1e-9)
    assert math.isclose(entries[2].duration_s, 1800.0, rel_tol=1e-9)

    assert entries[3].kind == TimelineKind.MARGIN
    assert math.isclose(entries[3].start_s, 4800.0, rel_tol=1e-9)
    assert math.isclose(entries[3].duration_s, 750.0, rel_tol=1e-9)

    assert entries[4].kind == TimelineKind.RESERVE
    assert math.isclose(entries[4].start_s, 5550.0, rel_tol=1e-9)
    assert math.isclose(entries[4].duration_s, 16050.0, rel_tol=1e-9)


def test_t_eva_05_timeline_negative_reserve_budget_exceeded() -> None:
    """T-EVA-05: When budget is exceeded, RESERVE duration is 0, totals keeps negative value.

    Hand Derivation:
        walk_time = 20000.0 s
        margin (1.25) = (1.25 - 1.0) * 20000.0 = 5000.0 s
        work_time = 0.0 s
        total_time = 20000.0 + 5000.0 = 25000.0 s
        time_available (6.0 h) = 21600.0 s
        reserve_remaining = 21600.0 - 25000.0 = -3400.0 s
    """
    config = get_default_eva_config()
    p0 = GeoPoint(lat=-4.75, lon=137.28)
    p1 = GeoPoint(lat=-4.76, lon=137.29)

    legs = [
        RouteLeg(
            from_label="base",
            to_label="destination",
            path=[p0, p1],
            horizontal_distance_m=10000.0,
            surface_distance_m=10100.0,
            ascent_m=100.0,
            descent_m=50.0,
            walk_time_s=20000.0,
        )
    ]

    entries, totals = compute_eva_timeline(
        legs=legs,
        stops=[],
        config=config,
        destination_work_time_min=0.0,
    )

    # Totals keeps exact negative reserve
    assert math.isclose(totals.total_time_s, 25000.0, rel_tol=1e-9)
    assert math.isclose(totals.reserve_remaining_s, -3400.0, rel_tol=1e-9)

    # Timeline RESERVE entry duration is clamped at 0.0 (cannot have negative duration block)
    reserve_entry = next(e for e in entries if e.kind == TimelineKind.RESERVE)
    assert math.isclose(reserve_entry.duration_s, 0.0, abs_tol=1e-9)
    assert math.isclose(reserve_entry.start_s, 25000.0, rel_tol=1e-9)


def test_timeline_destination_work_time_conditional() -> None:
    """Destination WORK entry is only included when destination has work time > 0."""
    config = get_default_eva_config()
    p0 = GeoPoint(lat=-4.75, lon=137.28)
    p1 = GeoPoint(lat=-4.76, lon=137.29)
    legs = [
        RouteLeg(
            from_label="base",
            to_label="destination",
            path=[p0, p1],
            horizontal_distance_m=1000.0,
            surface_distance_m=1000.0,
            ascent_m=0.0,
            descent_m=0.0,
            walk_time_s=1000.0,
        )
    ]

    # Case A: destination_work_time_min = 0.0 -> no destination WORK entry
    entries_a, totals_a = compute_eva_timeline(legs, [], config, destination_work_time_min=0.0)
    work_entries_a = [e for e in entries_a if e.kind == TimelineKind.WORK]
    assert len(work_entries_a) == 0
    assert totals_a.work_time_s == 0.0

    # Case B: destination_work_time_min = 15.0 min (900 s) -> destination WORK entry present
    entries_b, totals_b = compute_eva_timeline(legs, [], config, destination_work_time_min=15.0)
    work_entries_b = [e for e in entries_b if e.kind == TimelineKind.WORK]
    assert len(work_entries_b) == 1
    assert work_entries_b[0].label == "Work: Destination"
    assert math.isclose(work_entries_b[0].duration_s, 900.0, rel_tol=1e-9)
    assert math.isclose(totals_b.work_time_s, 900.0, rel_tol=1e-9)


def test_resolve_eva_config_override() -> None:
    """EvaConfigOverride selectively updates only overridden fields."""
    override = EvaConfigOverride(
        max_slope_deg=20.0,
        warning_slope_deg=12.0,
        max_eva_hours=4.5,
    )
    resolved = resolve_eva_config(override)
    assert resolved.max_slope_deg == 20.0
    assert resolved.warning_slope_deg == 12.0
    assert resolved.max_eva_hours == 4.5
    # Non-overridden fields keep defaults
    assert resolved.base_speed_kmh == 2.7
    assert resolved.return_reserve_fraction == 0.25


def test_roughness_warning_basis_matches_spec() -> None:
    """Basis text for roughness_warning_m in defaults.py must exactly match spec 6.2."""
    spec_path = Path(__file__).resolve().parents[4] / "docs" / "SCIENCE_AND_SAFETY_SPEC.md"
    if not spec_path.exists():
        pytest.skip("docs/SCIENCE_AND_SAFETY_SPEC.md not found from test location")

    spec_lines = spec_path.read_text(encoding="utf-8").splitlines()
    target_row = next(line for line in spec_lines if line.startswith("| `roughness_warning_m`"))
    # Row format: | `roughness_warning_m` | 0.30 | metres | ASSUMPTION | <basis> | — |
    parts = [p.strip() for p in target_row.split("|")]
    spec_basis = parts[5]

    records = {r.key: r for r in get_default_assumption_records()}
    assert records["roughness_warning_m"].basis == spec_basis
