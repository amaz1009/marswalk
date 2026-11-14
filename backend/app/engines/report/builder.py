"""Deterministic mission report builder implementing docs/SCIENCE_AND_SAFETY_SPEC.md §14.

Compiles MissionState, regional metadata, and catalog records into an integrated
MissionReport conforming to docs/API_CONTRACTS.md §4.13.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.engines.safety.checks import SAFETY_DISCLAIMER_TEXT
from app.models.datasets import DatasetRecord
from app.models.enums import AssessmentStatus, DataClass, PlanStatus
from app.models.evidence import AssumptionRecord
from app.models.mission import MissionReport, MissionState, ReportSection
from app.models.regions import RegionDetail
from app.services.eva_service import get_default_eva_response
from app.services.route_service import ENGINE_VERSION


def _format_coord(val: float | None, is_lat: bool = True) -> str:
    if val is None:
        return "UNKNOWN"
    hemisphere = ("N" if val >= 0 else "S") if is_lat else ("E" if val >= 0 else "W")
    return f"{abs(val):.4f}° {hemisphere}"


def build_mission_report(
    mission_state: MissionState,
    region: RegionDetail | dict[str, Any],
    catalog: list[DatasetRecord],
    *,
    now: datetime | None = None,
    id_factory: Callable[[], str] | None = None,
    engine_version: str = ENGINE_VERSION,
) -> MissionReport:
    """Build a deterministic mission report from mission state and regional data.

    Pure function: No raster reads, network calls, or LLM interactions.
    """
    report_time = now or datetime.now(timezone.utc)
    report_id = id_factory() if id_factory else f"rpt_{uuid.uuid4().hex[:12]}"

    # Extract region metadata
    if isinstance(region, RegionDetail):
        region_id = region.region_id
        region_name = region.name
        analysis_crs = region.analysis.analysis_crs if region.analysis else "UNKNOWN"
        science_targets = region.science_targets or []
    else:
        region_id = region.get("region_id", mission_state.region_id)
        region_name = region.get("name", region_id)
        analysis_dict = region.get("analysis", {})
        if isinstance(analysis_dict, dict):
            analysis_crs = analysis_dict.get("analysis_crs", "UNKNOWN")
        else:
            analysis_crs = "UNKNOWN"
        science_targets = region.get("science_targets", [])

    # Identify selected route if plan is present
    plan = mission_state.plan
    selected_route = None
    if plan and plan.routes and mission_state.selected_route_id:
        for r in plan.routes:
            if r.route_id == mission_state.selected_route_id:
                selected_route = r
                break

    # Build assumptions (R4)
    default_assumptions = get_default_eva_response().assumptions
    report_assumptions: list[AssumptionRecord] = []
    override_limitations: list[str] = []

    for rec in default_assumptions:
        active_val = getattr(mission_state.eva_config, rec.key, None)
        if active_val is not None and active_val != rec.value:
            report_assumptions.append(
                AssumptionRecord(
                    key=rec.key,
                    value=active_val,
                    units=rec.units,
                    data_class=DataClass.ASSUMPTION,
                    basis=f"user override of default {rec.value}",
                    citation=rec.citation,
                )
            )
            override_limitations.append(
                f"EvaConfig override: {rec.key} set to {active_val} (default {rec.value})"
            )
        else:
            report_assumptions.append(rec)

    # Compile limitations and unresolved issues
    collected_limitations: list[str] = list(override_limitations)
    collected_unresolved: list[str] = []

    if mission_state.base is None:
        collected_limitations.append("Base coordinate not configured (UNKNOWN)")
    if mission_state.destination is None:
        collected_limitations.append("Primary destination coordinate not configured (UNKNOWN)")
    if plan is None:
        collected_limitations.append("Traverse plan not calculated")
    elif plan.plan_status == PlanStatus.NO_FEASIBLE_ROUTE:
        reason_text = plan.blocking_reason or "Analysis window blocked"
        collected_unresolved.append(f"No feasible route found: {reason_text}")

    if selected_route is not None:
        if selected_route.limitations:
            collected_limitations.extend(selected_route.limitations)
        if selected_route.safety.overall_status == AssessmentStatus.BLOCKED:
            blocked_reasons = [
                f"{c.check_id}: {c.message}"
                for c in selected_route.safety.checks
                if c.status == AssessmentStatus.BLOCKED
            ]
            collected_unresolved.extend(blocked_reasons)
        elif selected_route.safety.overall_status == AssessmentStatus.WARNING:
            warn_reasons = [
                f"{c.check_id}: {c.message}"
                for c in selected_route.safety.checks
                if c.status == AssessmentStatus.WARNING
            ]
            collected_unresolved.extend(warn_reasons)

    # Add catalog dataset limitations for scope A
    collected_limitations.append(
        "DTM vertical datum is unverified; elevation values are referenced to local Martian sphere"
    )
    collected_limitations.append(
        "Residual roughness proxy evaluated at 1 m cell scale; "
        "small suit-scale obstacles may remain undetected"
    )

    sections: list[ReportSection] = []

    # 1. Overview (Order 1)
    if mission_state.base:
        b_lat = _format_coord(mission_state.base.lat, True)
        b_lon = _format_coord(mission_state.base.lon, False)
        base_str = f"{b_lat}, {b_lon}"
    else:
        base_str = "UNKNOWN (not configured)"

    if mission_state.destination:
        d_lat = _format_coord(mission_state.destination.lat, True)
        d_lon = _format_coord(mission_state.destination.lon, False)
        dest_str = f"{d_lat}, {d_lon}"
    else:
        dest_str = "UNKNOWN (not configured)"

    overview_lines = [
        f"- **Mission Name**: {mission_state.name}",
        f"- **Mission ID**: {mission_state.mission_id}",
        f"- **Exploration Region**: {region_name} (`{region_id}`)",
        f"- **Analysis Coordinate Reference System**: `{analysis_crs}`",
        f"- **Base Location**: {base_str}",
        f"- **Destination Location**: {dest_str}",
        f"- **Configured Stops Count**: {len(mission_state.stops)}",
        f"- **Report Generated UTC**: {report_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- **Engine Version**: {engine_version}",
    ]
    sections.append(
        ReportSection(
            section_id="overview",
            title="Overview",
            body_markdown="\n".join(overview_lines),
            data_class=DataClass.DERIVED,
        )
    )

    # 2. Science (Order 2)
    science_lines = [
        "### Science Objective",
        mission_state.objective_text,
        "",
        "### Traverse Stops & Science Targets",
    ]
    if mission_state.stops:
        science_lines.extend(
            [
                "| Stop # | Label | Latitude | Longitude | Duration (min) | Target Details | "
                "Data Class | Source |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for idx, stop in enumerate(mission_state.stops, start=1):
            s_lat = f"{stop.point.lat:.4f}°"
            s_lon = f"{stop.point.lon:.4f}°"
            s_dur = f"{stop.work_time_min:.1f}" if stop.work_time_min is not None else "Default"
            s_desc = getattr(stop, "description", None) or "Scientific observation waypoint"
            science_lines.append(
                f"| {idx} | {stop.name} | {s_lat} | {s_lon} | {s_dur} | {s_desc} | "
                f"REFERENCE | MissionState.stops |"
            )
    else:
        science_lines.append("No intermediate scientific waypoints configured.")

    if science_targets:
        science_lines.extend(
            [
                "",
                "### Regional Reference Targets",
                "| Target ID | Name | Latitude | Longitude | Description | Data Class | Source |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for st in science_targets:
            if isinstance(st, dict):
                t_id = st.get("target_id", "TARGET")
                t_name = st.get("name", t_id)
                pt = st.get("point", {})
                pt_lat = pt.get("lat", 0.0) if isinstance(pt, dict) else 0.0
                pt_lon = pt.get("lon", 0.0) if isinstance(pt, dict) else 0.0
                desc = st.get("description", "")
            else:
                t_id = getattr(st, "target_id", "TARGET")
                t_name = getattr(st, "name", t_id)
                pt = getattr(st, "point", None)
                pt_lat = pt.lat if pt else 0.0
                pt_lon = pt.lon if pt else 0.0
                desc = getattr(st, "description", "")
            science_lines.append(
                f"| {t_id} | {t_name} | {pt_lat:.4f}° | {pt_lon:.4f}° | {desc} | "
                f"REFERENCE | region.science_targets |"
            )

    sections.append(
        ReportSection(
            section_id="science",
            title="Science",
            body_markdown="\n".join(science_lines),
            data_class=DataClass.REFERENCE,
        )
    )

    # 3. Datasets (Order 3)
    dataset_lines = [
        "### Contributing Regional Datasets",
        "| Dataset ID | Mission | Instrument | Native Res | Status | "
        "Availability Reason & Limitations | Data Class | Source |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for ds in catalog:
        res_str = (
            f"{ds.native_resolution_m:.1f} m" if ds.native_resolution_m is not None else "Global"
        )
        status_val = ds.status.value if hasattr(ds.status, "value") else str(ds.status)
        reason_lim = ds.status_reason or "; ".join(ds.limitations) or "Nominal coverage"
        dataset_lines.append(
            f"| `{ds.dataset_id}` | {ds.mission} | {ds.instrument} | {res_str} | "
            f"{status_val} | {reason_lim} | REFERENCE | dataset_catalog.json |"
        )
    dataset_lines.extend(
        [
            "",
            "**Routing Engine Access:** Datasets read by routing engine: "
            "HIRISE_DTM_GALE_MOUND and the slope and roughness layers derived from it.",
        ]
    )
    sections.append(
        ReportSection(
            section_id="datasets",
            title="Datasets",
            body_markdown="\n".join(dataset_lines),
            data_class=DataClass.REFERENCE,
        )
    )

    # 4. Terrain (Order 4)
    if plan is None or selected_route is None:
        terrain_md = "Terrain summary along route: not computed because no route plan exists."
    else:
        sl = selected_route.slope_stats
        rg = selected_route.roughness_stats
        warn_pct = selected_route.fraction_above_warning_slope * 100.0
        w_deg = mission_state.eva_config.warning_slope_deg
        t_lines = [
            "### Terrain Statistics Along Traverse",
            "| Metric | Value | Units | Data Class | Source |",
            "|---|---|---|---|---|",
            f"| Maximum Slope | {sl.max:.2f} | degrees | DERIVED | HIRISE_DTM_GALE_MOUND |",
            f"| Mean Slope | {sl.mean:.2f} | degrees | DERIVED | HIRISE_DTM_GALE_MOUND |",
            f"| 95th Percentile Slope | {sl.p95:.2f} | degrees | DERIVED | HIRISE_DTM_GALE_MOUND |",
            f"| Fraction Above Warning Slope ({w_deg:.1f}°) | {warn_pct:.2f}% | "
            f"percentage | DERIVED | HIRISE_DTM_GALE_MOUND |",
            f"| Maximum Roughness | {rg.max:.3f} | metres | DERIVED | HIRISE_DTM_GALE_MOUND |",
            f"| Mean Roughness | {rg.mean:.3f} | metres | DERIVED | HIRISE_DTM_GALE_MOUND |",
            f"| 95th Percentile Roughness | {rg.p95:.3f} | metres | "
            f"DERIVED | HIRISE_DTM_GALE_MOUND |",
        ]
        if selected_route.elevation_profile:
            elevs = [
                p.elevation_m for p in selected_route.elevation_profile if p.elevation_m is not None
            ]
            if elevs:
                t_lines.extend(
                    [
                        "",
                        f"- **Starting Elevation:** {elevs[0]:.1f} m",
                        f"- **Final Elevation:** {elevs[-1]:.1f} m",
                        f"- **Minimum Elevation:** {min(elevs):.1f} m",
                        f"- **Maximum Elevation:** {max(elevs):.1f} m",
                    ]
                )
        terrain_md = "\n".join(t_lines)

    sections.append(
        ReportSection(
            section_id="terrain",
            title="Terrain",
            body_markdown=terrain_md,
            data_class=DataClass.DERIVED,
        )
    )

    # 5. Selected Route (Order 5)
    if plan is None:
        sel_md = "Selected route: not computed because no route plan exists."
    elif plan.plan_status == PlanStatus.NO_FEASIBLE_ROUTE:
        reason_str = plan.blocking_reason or "No path found"
        sel_md = (
            f"No route selected (plan status: NO_FEASIBLE_ROUTE; blocking reason: {reason_str})."
        )
    elif selected_route is None:
        sel_md = "No route selected."
    else:
        tot = selected_route.totals
        dur_min = tot.total_time_s / 60.0
        dur_h = tot.total_time_s / 3600.0
        max_d = selected_route.max_distance_from_base_m
        r_lines = [
            f"- **Selected Profile:** `{selected_route.objective.value}`",
            f"- **Horizontal Distance:** {tot.horizontal_distance_m:.1f} m "
            f"[MODEL, AresNav Planner]",
            f"- **Surface Distance:** {tot.surface_distance_m:.1f} m [MODEL, AresNav Planner]",
            f"- **Maximum Distance from Base:** {max_d:.1f} m [MODEL, AresNav Planner]",
            f"- **Estimated Total Time:** {dur_min:.1f} min ({dur_h:.2f} h) "
            f"[MODEL, Tobler Walking Model]",
            "",
            "### Traverse Legs Breakdown",
            "| Leg # | From | To | Surface Dist (m) | Ascent (m) | Descent (m) | "
            "Walk Time (min) | Data Class | Source |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for l_idx, leg in enumerate(selected_route.legs, start=1):
            walk_min = leg.walk_time_s / 60.0
            r_lines.append(
                f"| {l_idx} | {leg.from_label} | {leg.to_label} | {leg.surface_distance_m:.1f} | "
                f"{leg.ascent_m:.1f} | {leg.descent_m:.1f} | {walk_min:.1f} | "
                f"MODEL | AresNav Planner |"
            )
        if selected_route.limitations:
            r_lines.extend(
                ["", "### Route Limitations", *[f"- {lim}" for lim in selected_route.limitations]]
            )
        sel_md = "\n".join(r_lines)

    sections.append(
        ReportSection(
            section_id="selected_route",
            title="Selected Route",
            body_markdown=sel_md,
            data_class=DataClass.MODEL,
        )
    )

    # 6. EVA Timeline (Order 6)
    if plan is None or selected_route is None:
        timeline_md = "EVA timeline: not computed because no route plan exists."
    else:
        tot = selected_route.totals
        tl_lines = [
            "### Consumables & Timeline Budget",
            "| Phase | Duration (min) | Duration (h) | Data Class | Source |",
            "|---|---|---|---|---|",
            f"| Walking Duration | {tot.walk_time_s / 60.0:.1f} | {tot.walk_time_s / 3600.0:.2f} | "
            f"MODEL | Tobler Walking Model |",
            f"| Contingency Margin | {tot.margin_time_s / 60.0:.1f} | "
            f"{tot.margin_time_s / 3600.0:.2f} | MODEL | EVA Timeline Engine |",
            f"| Science Work Duration | {tot.work_time_s / 60.0:.1f} | "
            f"{tot.work_time_s / 3600.0:.2f} | MODEL | EvaConfig / Stops |",
            f"| Total Planned EVA Time | {tot.total_time_s / 60.0:.1f} | "
            f"{tot.total_time_s / 3600.0:.2f} | MODEL | EVA Timeline Engine |",
            f"| Time Available | {tot.time_available_s / 60.0:.1f} | "
            f"{tot.time_available_s / 3600.0:.2f} | ASSUMPTION | EvaConfig.max_eva_hours |",
            f"| Reserve Remaining | {tot.reserve_remaining_s / 60.0:.1f} | "
            f"{tot.reserve_remaining_s / 3600.0:.2f} | MODEL | EVA Timeline Engine |",
            "",
            "### Detailed Timeline Schedule",
            "| Step | Event Kind | Label | Start (min) | Duration (min) | Data Class | Source |",
            "|---|---|---|---|---|---|---|",
        ]
        for s_idx, t_entry in enumerate(selected_route.timeline, start=1):
            tl_lines.append(
                f"| {s_idx} | {t_entry.kind.value} | {t_entry.label} | "
                f"{t_entry.start_s / 60.0:.1f} | {t_entry.duration_s / 60.0:.1f} | "
                f"MODEL | EVA Timeline Engine |"
            )
        timeline_md = "\n".join(tl_lines)

    sections.append(
        ReportSection(
            section_id="eva_timeline",
            title="EVA Timeline",
            body_markdown=timeline_md,
            data_class=DataClass.MODEL,
        )
    )

    # 7. Safety (Order 7)
    if plan is None or selected_route is None:
        safety_md = (
            "Overall Safety Status: UNKNOWN (not computed because no route plan exists).\n\n"
            "Data are insufficient to evaluate safety constraints; treat as unverified."
        )
    else:
        sf = selected_route.safety
        s_lines: list[str] = []

        if sf.overall_status == AssessmentStatus.BLOCKED:
            blocked_checks = [c for c in sf.checks if c.status == AssessmentStatus.BLOCKED]
            blocked_details = ", ".join(
                f"{c.check_id.value if hasattr(c.check_id, 'value') else c.check_id} "
                f"(value={c.value}, limit={c.threshold})"
                for c in blocked_checks
            )
            s_lines.extend(
                [
                    "Overall Safety Status: BLOCKED.",
                    "At least one hard safety constraint is violated; route not recommended.",
                    f"Violated checks: {blocked_details}.",
                ]
            )
        elif sf.overall_status == AssessmentStatus.WARNING:
            warn_checks = [c for c in sf.checks if c.status == AssessmentStatus.WARNING]
            warn_details = ", ".join(
                f"{c.check_id.value if hasattr(c.check_id, 'value') else c.check_id} ({c.message})"
                for c in warn_checks
            )
            s_lines.extend(
                [
                    "Overall Safety Status: WARNING.",
                    "No hard safety constraint is violated; advisory conditions were detected: "
                    f"{warn_details}. Review is recommended before execution.",
                ]
            )
        elif sf.overall_status == AssessmentStatus.PASS:
            s_lines.extend(
                [
                    "Overall Safety Status: PASS.",
                    "The traverse meets the configured prototype criteria with no constraint "
                    "violations detected.",
                ]
            )
        else:
            s_lines.extend(
                [
                    "Overall Safety Status: UNKNOWN.",
                    "Data are insufficient to evaluate safety constraints; treat as unverified.",
                ]
            )

        s_lines.extend(
            [
                "",
                "### Safety Checks Assessment",
                "| Check ID | Status | Measured / Computed | Threshold | Units | "
                "Assessment Message | Data Class | Source |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for chk in sf.checks:
            chk_id_str = chk.check_id.value if hasattr(chk.check_id, "value") else str(chk.check_id)
            v_str = f"{chk.value:.2f}" if chk.value is not None else "None"
            th_str = f"{chk.threshold:.2f}" if chk.threshold is not None else "None"
            u_str = chk.units or "—"
            src_str = chk.evidence[0].source_id if chk.evidence else "app.engines.safety"
            s_lines.append(
                f"| `{chk_id_str}` | {chk.status.value} | {v_str} | {th_str} | {u_str} | "
                f"{chk.message} | DERIVED | {src_str} |"
            )

        s_lines.extend(
            [
                "",
                "### Environmental Context Indicators",
                "- **Radiation Context (`MSL_RAD_SURFACE_RDR`):** UNAVAILABLE "
                "(historical surface radiation observations from MSL Curiosity are "
                "unavailable in Scope A).",
                "- **Thermal Context (`THEMIS_DAY_IR_GLOBAL`):** UNAVAILABLE "
                "(orbital diurnal infrared observations are unavailable in Scope A).",
            ]
        )
        safety_md = "\n".join(s_lines)

    sections.append(
        ReportSection(
            section_id="safety",
            title="Safety",
            body_markdown=safety_md,
            data_class=DataClass.DERIVED,
        )
    )

    # 8. Alternatives (Order 8)
    if plan is None:
        alt_md = "Traverse alternatives: not computed because no route plan exists."
    elif plan.plan_status == PlanStatus.NO_FEASIBLE_ROUTE:
        reason_str = plan.blocking_reason or "Terrain obstacles prevented routing"
        alt_md = f"No feasible routes found within analysis window. Blocking reason: {reason_str}."
    else:
        alt_lines = [
            "### Computed Traverse Profiles",
            "| Route ID | Objective | Safety Status | Surface Dist (m) | Max Slope (deg) | "
            "Total Time (h) | Reserve Rem (min) | Identical To | Data Class | Source |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for rt in plan.routes:
            r_tot = rt.totals
            r_sl = rt.slope_stats
            r_time_h = r_tot.total_time_s / 3600.0
            r_res_min = r_tot.reserve_remaining_s / 60.0
            dup = rt.identical_to or "None"
            alt_lines.append(
                f"| `{rt.route_id}` | {rt.objective.value} | {rt.safety.overall_status.value} | "
                f"{r_tot.surface_distance_m:.1f} | {r_sl.max:.2f} | {r_time_h:.2f} | "
                f"{r_res_min:.1f} | {dup} | MODEL | AresNav Planner |"
            )

        if plan.omitted_objectives:
            alt_lines.extend(
                [
                    "",
                    "### Omitted Profiles",
                    "| Objective | Reason | Data Class | Source |",
                    "|---|---|---|---|",
                ]
            )
            for omit in plan.omitted_objectives:
                alt_lines.append(
                    f"| {omit.objective.value} | {omit.reason} | DERIVED | AresNav Planner |"
                )

        alt_md = "\n".join(alt_lines)

    sections.append(
        ReportSection(
            section_id="alternatives",
            title="Alternatives",
            body_markdown=alt_md,
            data_class=DataClass.MODEL,
        )
    )

    # 9. Assumptions (Order 9)
    assump_lines = [
        "### Applied Operational & Scientific Assumptions",
        "| Parameter Key | Active Value | Units | Data Class | Basis | Citation |",
        "|---|---|---|---|---|---|",
    ]
    for asmp in report_assumptions:
        u_str = asmp.units or "—"
        cit_str = asmp.citation or "—"
        assump_lines.append(
            f"| `{asmp.key}` | {asmp.value} | {u_str} | {asmp.data_class.value} | "
            f"{asmp.basis} | {cit_str} |"
        )
    sections.append(
        ReportSection(
            section_id="assumptions",
            title="Assumptions",
            body_markdown="\n".join(assump_lines),
            data_class=DataClass.ASSUMPTION,
        )
    )

    # 10. Limitations (Order 10)
    lim_lines = ["### Operational Limitations & Technical Notes"]
    for lim in collected_limitations:
        lim_lines.append(f"- {lim}")

    if collected_unresolved:
        lim_lines.extend(["", "### Unresolved Issues & Safety Concerns"])
        for unr in collected_unresolved:
            lim_lines.append(f"- {unr}")

    sections.append(
        ReportSection(
            section_id="limitations",
            title="Limitations",
            body_markdown="\n".join(lim_lines),
            data_class=DataClass.DERIVED,
        )
    )

    # 11. AI Interpretation (Order 11 - present ONLY when agent_analysis is provided)
    if mission_state.agent_analysis is not None:
        aa = mission_state.agent_analysis
        ai_lines = [
            "This section is an AI interpretation of mission data and does not change "
            "any safety status or check result.",
            "",
            "### Synthesis Summary",
            aa.synthesis.summary,
        ]
        if aa.synthesis.recommendations:
            ai_lines.extend(["", "### Recommendations"])
            for rec_text in aa.synthesis.recommendations:
                ai_lines.append(f"- {rec_text}")
        if aa.synthesis.unresolved_issues:
            ai_lines.extend(["", "### Open Questions"])
            for issue_text in aa.synthesis.unresolved_issues:
                ai_lines.append(f"- {issue_text}")

        sections.append(
            ReportSection(
                section_id="ai_interpretation",
                title="AI Interpretation",
                body_markdown="\n".join(ai_lines),
                data_class=DataClass.AI_INTERPRETATION,
            )
        )

    # 12. Disclaimer (Order 12)
    sections.append(
        ReportSection(
            section_id="disclaimer",
            title="Disclaimer",
            body_markdown=SAFETY_DISCLAIMER_TEXT,
            data_class=DataClass.REFERENCE,
        )
    )

    # Concatenate full Markdown (R14)
    markdown_parts = [
        f"# Mission Report: {mission_state.name}\n\n",
    ]
    for sec in sections:
        markdown_parts.append(f"## {sec.title}\n\n{sec.body_markdown}\n\n")

    full_markdown = "".join(markdown_parts).strip() + "\n"

    return MissionReport(
        report_id=report_id,
        generated_at=report_time,
        mission_id=mission_state.mission_id,
        disclaimer=SAFETY_DISCLAIMER_TEXT,
        sections=sections,
        datasets=catalog,
        assumptions=report_assumptions,
        limitations=collected_limitations,
        unresolved_issues=collected_unresolved,
        markdown=full_markdown,
        engine_version=engine_version,
    )
