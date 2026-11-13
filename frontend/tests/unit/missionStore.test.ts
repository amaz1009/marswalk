import { describe, it, expect, beforeEach } from 'vitest';
import { useMissionStore } from '../../src/store/missionStore';
import type { components } from '../../src/types/api.gen';

// Test fixture only, not a source of defaults; real defaults come from GET /eva/defaults.
const TEST_EVA_CONFIG: components['schemas']['EvaConfig'] = {
  base_speed_kmh: 2.7,
  default_work_time_min: 20,
  max_distance_from_base_m: 2000,
  max_eva_hours: 6.0,
  max_slope_deg: 15,
  return_reserve_fraction: 0.25,
  roughness_warning_m: 0.30,
  traverse_time_margin: 1.25,
  warning_slope_deg: 10,
};

describe('MissionStore (WP-04)', () => {
  beforeEach(() => {
    // Reset store to known baseline
    useMissionStore.setState({
      mission_id: null,
      name: null,
      created_at: null,
      region_id: 'gale_mount_sharp',
      objective_text: null,
      base: null,
      destination: null,
      stops: [],
      eva_config: null,
      plan: null,
      selected_route_id: null,
      envelope: null,
      agent_analysis: null,
      notes: null,
      health: null,
      isBackendHealthy: false,
      selectedPoint: null,
      pointInspection: null,
      report: null,
      isLoading: false,
      errorMessage: null,
    });
  });

  it('has expected initial state and returns null for toMissionState()', () => {
    const state = useMissionStore.getState();

    expect(state.region_id).toBe('gale_mount_sharp');
    expect(state.mission_id).toBeNull();
    expect(state.name).toBeNull();
    expect(state.created_at).toBeNull();
    expect(state.objective_text).toBeNull();
    expect(state.eva_config).toBeNull();
    expect(state.stops).toEqual([]);
    expect(state.health).toBeNull();
    expect(state.isBackendHealthy).toBe(false);
    expect(state.toMissionState()).toBeNull();
  });

  it('sets isBackendHealthy to true on ok health response, and false on null', () => {
    const { setHealth } = useMissionStore.getState();

    const okHealth: components['schemas']['HealthResponse'] = {
      status: 'ok',
      version: '0.1.0',
      llm_mode: 'DISABLED',
      llm_provider: null,
      regions_loaded: 1,
      datasets_available: 3,
      datasets_unavailable: 0,
    };

    setHealth(okHealth);
    expect(useMissionStore.getState().isBackendHealthy).toBe(true);
    expect(useMissionStore.getState().health?.status).toBe('ok');

    setHealth(null);
    expect(useMissionStore.getState().isBackendHealthy).toBe(false);
    expect(useMissionStore.getState().health).toBeNull();
  });

  it('resetMission clears the plan, report, envelope, selection, and inspection', () => {
    const store = useMissionStore.getState();

    useMissionStore.setState({
      selected_route_id: 'rte_test_123',
      selectedPoint: { lat: -5.4, lon: 137.8 },
      plan: {
        plan_id: 'pln_123',
        region_id: 'gale_mount_sharp',
        plan_status: 'OK',
        blocking_reason: null,
        routes: [],
        omitted_objectives: [],
        eva_config: TEST_EVA_CONFIG,
        assumptions: [],
        grid: {
          analysis_crs: 'IAU2000:49900',
          cell_size_m: 10,
          rows: 100,
          cols: 100,
        },
        computed_at: '2026-11-14T09:00:00Z',
        engine_version: '0.1.0',
      },
      report: {
        report_id: 'rpt_123',
        generated_at: '2026-11-14T09:00:00Z',
        mission_id: 'msn_123',
        disclaimer: 'Prototype disclaimer',
        sections: [],
        datasets: [],
        assumptions: [],
        limitations: [],
        unresolved_issues: [],
        markdown: '# Report',
        engine_version: '0.1.0',
      },
      envelope: {
        envelope_id: 'env_123',
        bounds: { lat_min: -5.5, lat_max: -5.3, lon_min: 137.7, lon_max: 137.9 },
        image_png_base64: 'base64...',
        reachable_area_km2: 12.5,
        max_reach_m: 4500,
        eva_config: TEST_EVA_CONFIG,
        assumptions: [],
        limitations: [],
        computed_at: '2026-11-14T09:00:00Z',
      },
    });

    store.resetMission();

    const afterReset = useMissionStore.getState();
    expect(afterReset.plan).toBeNull();
    expect(afterReset.report).toBeNull();
    expect(afterReset.envelope).toBeNull();
    expect(afterReset.selected_route_id).toBeNull();
    expect(afterReset.selectedPoint).toBeNull();
  });

  it('toMissionState returns null when required fields (e.g. region or evaConfig) are missing', () => {
    const store = useMissionStore.getState();

    // Mission fields set, but evaConfig is null
    store.setMissionInfo({
      mission_id: 'msn_001',
      name: 'EVA-1 Exploration',
      created_at: '2026-11-14T09:30:00Z',
      objective_text: 'Sample Mount Sharp layers',
    });
    expect(store.toMissionState()).toBeNull();

    // Set evaConfig, but unset region_id
    store.setEvaConfig(TEST_EVA_CONFIG);
    store.setRegionId(null);
    expect(store.toMissionState()).toBeNull();
  });

  it('toMissionState returns complete MissionState object when all required fields are set', () => {
    const store = useMissionStore.getState();

    store.setRegionId('gale_mount_sharp');
    store.setMissionInfo({
      mission_id: 'msn_001',
      name: 'EVA-1 Exploration',
      created_at: '2026-11-14T09:30:00Z',
      objective_text: 'Sample Mount Sharp layers',
      notes: 'Initial deployment test',
    });
    store.setEvaConfig(TEST_EVA_CONFIG);
    store.setBase({ lat: -5.4, lon: 137.8 });
    store.setDestination({ lat: -5.35, lon: 137.85 });
    store.setStops([]);

    const missionState = store.toMissionState();
    expect(missionState).not.toBeNull();
    expect(missionState?.mission_id).toBe('msn_001');
    expect(missionState?.name).toBe('EVA-1 Exploration');
    expect(missionState?.created_at).toBe('2026-11-14T09:30:00Z');
    expect(missionState?.region_id).toBe('gale_mount_sharp');
    expect(missionState?.objective_text).toBe('Sample Mount Sharp layers');
    expect(missionState?.eva_config).toEqual(TEST_EVA_CONFIG);
    expect(missionState?.base).toEqual({ lat: -5.4, lon: 137.8 });
    expect(missionState?.destination).toEqual({ lat: -5.35, lon: 137.85 });
    expect(missionState?.stops).toEqual([]);
    expect(missionState?.notes).toBe('Initial deployment test');
  });
});
