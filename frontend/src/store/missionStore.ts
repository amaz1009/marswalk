import { create } from 'zustand';
import type { components } from '../types/api.gen';

export type HealthResponse = components['schemas']['HealthResponse'];
export type RegionSummary = components['schemas']['RegionSummary'];
export type RegionDetail = components['schemas']['RegionDetail'];
export type LayerInfo = components['schemas']['LayerInfo'];
export type PointInspection = components['schemas']['PointInspection'];
export type RoutePlanResponse = components['schemas']['RoutePlanResponse'];
export type MissionReport = components['schemas']['MissionReport'];
export type EnvelopeResponse = components['schemas']['EnvelopeResponse'];
export type GeoPoint = components['schemas']['GeoPoint'];

export interface MissionState {
  // Connection / System status
  health: HealthResponse | null;
  isBackendHealthy: boolean;

  // Region and Layers
  selectedRegionId: string | null;
  regionDetail: RegionDetail | null;
  availableRegions: RegionSummary[];
  layers: LayerInfo[];
  activeLayerIds: string[];

  // Inspection
  selectedPoint: GeoPoint | null;
  pointInspection: PointInspection | null;

  // Plan & Routes
  plan: RoutePlanResponse | null;
  selectedRouteId: string | null;

  // Envelope & Report
  envelope: EnvelopeResponse | null;
  report: MissionReport | null;

  // Loading & Error states
  isLoading: boolean;
  errorMessage: string | null;

  // Actions
  setHealth: (health: HealthResponse | null) => void;
  setSelectedRegionId: (regionId: string | null) => void;
  setSelectedPoint: (point: GeoPoint | null) => void;
  setPointInspection: (inspection: PointInspection | null) => void;
  setPlan: (plan: RoutePlanResponse | null) => void;
  setSelectedRouteId: (routeId: string | null) => void;
  resetMission: () => void;
}

export const useMissionStore = create<MissionState>((set) => ({
  health: null,
  isBackendHealthy: false,

  selectedRegionId: 'gale_mount_sharp',
  regionDetail: null,
  availableRegions: [],
  layers: [],
  activeLayerIds: [],

  selectedPoint: null,
  pointInspection: null,

  plan: null,
  selectedRouteId: null,

  envelope: null,
  report: null,

  isLoading: false,
  errorMessage: null,

  setHealth: (health) =>
    set({
      health,
      isBackendHealthy: health !== null && health.status === 'ok',
    }),

  setSelectedRegionId: (selectedRegionId) => set({ selectedRegionId }),
  setSelectedPoint: (selectedPoint) => set({ selectedPoint }),
  setPointInspection: (pointInspection) => set({ pointInspection }),
  setPlan: (plan) => set({ plan }),
  setSelectedRouteId: (selectedRouteId) => set({ selectedRouteId }),

  resetMission: () =>
    set({
      selectedPoint: null,
      pointInspection: null,
      plan: null,
      selectedRouteId: null,
      envelope: null,
      report: null,
      errorMessage: null,
    }),
}));
