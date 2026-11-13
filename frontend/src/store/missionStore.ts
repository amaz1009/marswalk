import { create } from 'zustand';
import type { components } from '../types/api.gen';

export type MissionStateContract = components['schemas']['MissionState'];
export type HealthResponse = components['schemas']['HealthResponse'];
export type RegionSummary = components['schemas']['RegionSummary'];
export type RegionDetail = components['schemas']['RegionDetail'];
export type LayerInfo = components['schemas']['LayerInfo'];
export type PointInspection = components['schemas']['PointInspection'];
export type RoutePlanResponse = components['schemas']['RoutePlanResponse'];
export type MissionReport = components['schemas']['MissionReport'];
export type EnvelopeResponse = components['schemas']['EnvelopeResponse'];
export type AgentAnalysisResponse = components['schemas']['AgentAnalysisResponse'];
export type GeoPoint = components['schemas']['GeoPoint'];
export type Stop = components['schemas']['Stop'];
export type EvaConfig = components['schemas']['EvaConfig'];

export interface MissionStoreState {
  // --- MissionState Contract Fields (API_CONTRACTS.md §3.7) ---
  mission_id: string | null;
  name: string | null;
  created_at: string | null;
  region_id: string | null;
  objective_text: string | null;
  base: GeoPoint | null;
  destination: GeoPoint | null;
  stops: Stop[];
  eva_config: EvaConfig | null;
  plan: RoutePlanResponse | null;
  selected_route_id: string | null;
  envelope: EnvelopeResponse | null;
  agent_analysis: AgentAnalysisResponse | null;
  notes: string | null;

  // --- UI and Loading State (kept separate) ---
  health: HealthResponse | null;
  isBackendHealthy: boolean;
  regionDetail: RegionDetail | null;
  availableRegions: RegionSummary[];
  layers: LayerInfo[];
  activeLayerIds: string[];
  selectedPoint: GeoPoint | null;
  pointInspection: PointInspection | null;
  report: MissionReport | null;
  isLoading: boolean;
  errorMessage: string | null;

  // --- Actions & Setters ---
  setHealth: (health: HealthResponse | null) => void;
  setRegionId: (region_id: string | null) => void;
  setSelectedRegionId: (region_id: string | null) => void;
  setMissionInfo: (info: {
    mission_id?: string | null;
    name?: string | null;
    created_at?: string | null;
    objective_text?: string | null;
    notes?: string | null;
  }) => void;
  setBase: (base: GeoPoint | null) => void;
  setDestination: (destination: GeoPoint | null) => void;
  setStops: (stops: Stop[]) => void;
  setEvaConfig: (eva_config: EvaConfig | null) => void;
  setPlan: (plan: RoutePlanResponse | null) => void;
  setSelectedRouteId: (selected_route_id: string | null) => void;
  setEnvelope: (envelope: EnvelopeResponse | null) => void;
  setAgentAnalysis: (agent_analysis: AgentAnalysisResponse | null) => void;
  setNotes: (notes: string | null) => void;
  setSelectedPoint: (point: GeoPoint | null) => void;
  setPointInspection: (inspection: PointInspection | null) => void;
  setReport: (report: MissionReport | null) => void;
  resetMission: () => void;
  toMissionState: () => MissionStateContract | null;
}

export const useMissionStore = create<MissionStoreState>((set, get) => ({
  // MissionState contract fields initial values
  mission_id: null,
  name: null,
  created_at: null,
  // Region ID fixed by docs/API_CONTRACTS.md:725 and docs/DATA_SOURCES.md:29
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

  // UI & Loading state initial values
  health: null,
  isBackendHealthy: false,
  regionDetail: null,
  availableRegions: [],
  layers: [],
  activeLayerIds: [],
  selectedPoint: null,
  pointInspection: null,
  report: null,
  isLoading: false,
  errorMessage: null,

  setHealth: (health) =>
    set({
      health,
      isBackendHealthy: health !== null && health.status === 'ok',
    }),

  setRegionId: (region_id) => set({ region_id }),
  setSelectedRegionId: (region_id) => set({ region_id }),

  setMissionInfo: (info) =>
    set((state) => ({
      mission_id: info.mission_id !== undefined ? info.mission_id : state.mission_id,
      name: info.name !== undefined ? info.name : state.name,
      created_at: info.created_at !== undefined ? info.created_at : state.created_at,
      objective_text:
        info.objective_text !== undefined ? info.objective_text : state.objective_text,
      notes: info.notes !== undefined ? info.notes : state.notes,
    })),

  setBase: (base) => set({ base }),
  setDestination: (destination) => set({ destination }),
  setStops: (stops) => set({ stops }),
  setEvaConfig: (eva_config) => set({ eva_config }),
  setPlan: (plan) => set({ plan }),
  setSelectedRouteId: (selected_route_id) => set({ selected_route_id }),
  setEnvelope: (envelope) => set({ envelope }),
  setAgentAnalysis: (agent_analysis) => set({ agent_analysis }),
  setNotes: (notes) => set({ notes }),
  setSelectedPoint: (selectedPoint) => set({ selectedPoint }),
  setPointInspection: (pointInspection) => set({ pointInspection }),
  setReport: (report) => set({ report }),

  resetMission: () =>
    set({
      plan: null,
      selected_route_id: null,
      envelope: null,
      agent_analysis: null,
      report: null,
      selectedPoint: null,
      pointInspection: null,
      errorMessage: null,
    }),

  toMissionState: (): MissionStateContract | null => {
    const state = get();
    if (
      !state.mission_id ||
      !state.created_at ||
      !state.name ||
      !state.region_id ||
      !state.objective_text ||
      !state.eva_config ||
      !Array.isArray(state.stops)
    ) {
      return null;
    }
    return {
      mission_id: state.mission_id,
      created_at: state.created_at,
      name: state.name,
      region_id: state.region_id,
      objective_text: state.objective_text,
      stops: state.stops,
      eva_config: state.eva_config,
      base: state.base,
      destination: state.destination,
      plan: state.plan,
      selected_route_id: state.selected_route_id,
      envelope: state.envelope,
      agent_analysis: state.agent_analysis,
      notes: state.notes,
    };
  },
}));
