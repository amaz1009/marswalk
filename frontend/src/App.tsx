import React, { useEffect, useState } from 'react';
import { MapContainer } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { apiClient } from './services/apiClient';
import { useMissionStore } from './store/missionStore';
import { Activity, ShieldAlert, Cpu, Layers, Crosshair, Compass } from 'lucide-react';

// ASSUMPTION: placeholder initial view; real region bounds come from /regions
const INITIAL_VIEW_CENTER: [number, number] = [-5.4, 137.8];

export const App: React.FC = () => {
  const { health, isBackendHealthy, setHealth } = useMissionStore();
  const [isConnecting, setIsConnecting] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const fetchHealth = async () => {
      try {
        const response = await apiClient.getHealth();
        if (isMounted) {
          setHealth(response);
          setIsConnecting(false);
        }
      } catch {
        if (isMounted) {
          setHealth(null);
          setIsConnecting(false);
        }
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 10000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [setHealth]);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0c0d10] text-gray-200 overflow-hidden font-sans select-none">
      {/* Top Bar */}
      <header className="h-14 border-b border-[#282c37] bg-[#12141a] px-4 flex items-center justify-between z-20 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <span className="h-3 w-3 rounded-full bg-[#d9532f] inline-block animate-pulse" />
            <h1 className="text-lg font-bold tracking-wider text-white">MARSWALK</h1>
          </div>
          <span className="text-xs px-2 py-0.5 rounded bg-[#1e222d] text-gray-400 border border-[#2e3444]">
            Human-EVA Mission Control
          </span>
          <span className="text-xs text-gray-400">
            Region: <strong className="text-gray-200">Gale / Mount Sharp</strong>
          </span>
        </div>

        {/* Health & LLM Mode Indicators */}
        <div className="flex items-center space-x-3 text-xs">
          {/* Health Indicator */}
          <div
            data-testid="health-indicator"
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded border ${
              isConnecting
                ? 'bg-yellow-950/40 border-yellow-700/50 text-yellow-300'
                : isBackendHealthy
                ? 'bg-emerald-950/40 border-emerald-700/50 text-emerald-300'
                : 'bg-red-950/40 border-red-700/50 text-red-300'
            }`}
          >
            <Activity className="h-3.5 w-3.5" />
            <span className="font-mono">
              {isConnecting
                ? 'CONNECTING...'
                : isBackendHealthy
                ? `BACKEND: OK (v${health?.version})`
                : 'BACKEND: OFFLINE'}
            </span>
          </div>

          {/* LLM Mode Indicator */}
          <div
            data-testid="llm-indicator"
            className="flex items-center space-x-1.5 px-2.5 py-1 rounded border bg-[#1a1e29] border-[#2c3345] text-cyan-300"
          >
            <Cpu className="h-3.5 w-3.5" />
            <span className="font-mono">
              LLM: {health ? health.llm_mode : 'UNKNOWN'}
            </span>
          </div>

          {/* Data Status Indicator */}
          <div
            data-testid="dataset-indicator"
            className="hidden md:flex items-center space-x-2 text-gray-400 border-l border-[#282c37] pl-3"
          >
            {health ? (
              <>
                <span>Datasets: {health.datasets_available} avail</span>
                <span>/</span>
                <span>{health.datasets_unavailable} unavail</span>
              </>
            ) : (
              <span>Datasets: unknown</span>
            )}
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Panel: Layers and Region Controls */}
        <aside className="w-72 border-r border-[#282c37] bg-[#12141a] flex flex-col z-10 shrink-0">
          <div className="p-3 border-b border-[#282c37] flex items-center justify-between bg-[#161822]">
            <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-gray-300">
              <Layers className="h-4 w-4 text-[#d9532f]" />
              <span>Layers & Products</span>
            </div>
          </div>
          <div className="p-4 flex-1 overflow-y-auto space-y-4 text-xs text-gray-400">
            <div className="p-3 rounded bg-[#181b24] border border-[#252a38] text-gray-300">
              Region: Gale / Mount Sharp. No region data loaded yet.
            </div>
            <div className="p-3 rounded border border-dashed border-[#2d3242] text-center text-gray-500">
              No data layers loaded yet.
            </div>
          </div>
        </aside>

        {/* Center: Leaflet Mars Map */}
        <main className="flex-1 relative h-full bg-[#0a0b0e] overflow-hidden">
          <MapContainer
            center={INITIAL_VIEW_CENTER}
            zoom={9}
            crs={L.CRS.EPSG4326}
            zoomControl={true}
            attributionControl={false}
            className="w-full h-full"
          >
            {/* 
              No Earth basemap tiles or place labels.
              Mars coordinate display only. Data overlays will load via layer endpoints.
            */}
          </MapContainer>

          {/* Coordinate HUD Overlay */}
          <div className="absolute top-3 left-14 z-[400] bg-[#12141acc] backdrop-blur-sm border border-[#282c37] rounded px-3 py-1.5 text-xs font-mono text-gray-300 flex items-center space-x-2">
            <Compass className="h-3.5 w-3.5 text-[#d9532f]" />
            <span>Mars map: no data layers loaded</span>
          </div>
        </main>

        {/* Right Panel: Point Inspector & Safety Assessment */}
        <aside className="w-80 border-l border-[#282c37] bg-[#12141a] flex flex-col z-10 shrink-0">
          <div className="p-3 border-b border-[#282c37] flex items-center justify-between bg-[#161822]">
            <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-gray-300">
              <Crosshair className="h-4 w-4 text-[#d9532f]" />
              <span>Inspector & Evidence</span>
            </div>
          </div>
          <div className="p-4 flex-1 overflow-y-auto space-y-4 text-xs text-gray-400">
            <div className="p-3 rounded bg-[#181b24] border border-[#252a38] space-y-2">
              <div className="text-gray-300 font-medium flex items-center space-x-1.5">
                <ShieldAlert className="h-4 w-4 text-amber-500" />
                <span>Safety Verification</span>
              </div>
              <p className="text-gray-400 leading-relaxed">
                Point sampling and route safety constraints will be evaluated here upon point click or route selection.
              </p>
            </div>
            <div className="p-3 rounded border border-dashed border-[#2d3242] text-center text-gray-500">
              Awaiting terrain point inspection. No data loaded yet.
            </div>
          </div>
        </aside>
      </div>

      {/* Bottom Drawer: Traverse Planner / Elevation Profile */}
      <footer className="h-32 border-t border-[#282c37] bg-[#12141a] px-4 py-2 z-20 shrink-0 flex flex-col">
        <div className="flex items-center justify-between text-xs border-b border-[#202430] pb-1.5 text-gray-400">
          <span className="font-semibold text-gray-300">Traverse Planner & Profile</span>
          <span>No route planned</span>
        </div>
        <div className="flex-1 flex items-center justify-center text-xs text-gray-500">
          Elevation profiles, EVA timeline, and three-route comparison appear here after route generation.
        </div>
      </footer>
    </div>
  );
};

export default App;
