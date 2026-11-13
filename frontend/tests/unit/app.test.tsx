import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import L from 'leaflet';
import App from '../../src/App';
import { apiClient } from '../../src/services/apiClient';
import { useMissionStore } from '../../src/store/missionStore';

let capturedMapProps: { crs?: unknown; children?: React.ReactNode } = {};

vi.mock('react-leaflet', () => ({
  MapContainer: (props: { children?: React.ReactNode; crs?: unknown }) => {
    capturedMapProps = props;
    return <div data-testid="leaflet-map">{props.children}</div>;
  },
}));

describe('App Layout Shell (WP-04)', () => {
  beforeEach(() => {
    capturedMapProps = {};
    useMissionStore.getState().setHealth(null);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('configures Leaflet map with L.CRS.EPSG4326 and no children (no Earth tile layers)', () => {
    vi.spyOn(apiClient, 'getHealth').mockReturnValue(new Promise(() => {}));
    render(<App />);

    expect(capturedMapProps.crs).toBe(L.CRS.EPSG4326);
    expect(React.Children.count(capturedMapProps.children)).toBe(0);
    expect(screen.getByText('Mars map: no data layers loaded')).toBeInTheDocument();
  });

  it('displays pending state when health check is unresolved', () => {
    vi.spyOn(apiClient, 'getHealth').mockReturnValue(new Promise(() => {}));
    render(<App />);

    expect(screen.getByText(/CONNECTING.../i)).toBeInTheDocument();
    expect(screen.getByText(/LLM:\s*UNKNOWN/i)).toBeInTheDocument();
    expect(screen.getByText(/Datasets:\s*unknown/i)).toBeInTheDocument();
  });

  it('displays backend OK and LLM mode when health check resolves ok', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'ok',
      version: '0.1.0',
      llm_mode: 'DISABLED',
      llm_provider: null,
      regions_loaded: 1,
      datasets_available: 5,
      datasets_unavailable: 1,
    });

    render(<App />);

    expect(await screen.findByText(/BACKEND:\s*OK\s*\(v0\.1\.0\)/i)).toBeInTheDocument();
    expect(screen.getByText(/LLM:\s*DISABLED/i)).toBeInTheDocument();
    expect(screen.getByText(/Datasets:\s*5\s*avail/i)).toBeInTheDocument();
    expect(screen.getByText(/1\s*unavail/i)).toBeInTheDocument();
  });

  it('displays backend OFFLINE and UNKNOWN indicators when health check is rejected', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue(new Error('Backend connection failed'));

    render(<App />);

    expect(await screen.findByText(/BACKEND:\s*OFFLINE/i)).toBeInTheDocument();
    expect(screen.getByText(/LLM:\s*UNKNOWN/i)).toBeInTheDocument();
    expect(screen.getByText(/Datasets:\s*unknown/i)).toBeInTheDocument();
  });

  it('renders side panels and bottom drawer with neutral, unsourced-free wording', () => {
    vi.spyOn(apiClient, 'getHealth').mockReturnValue(new Promise(() => {}));
    render(<App />);

    expect(
      screen.getByText('Region: Gale / Mount Sharp. No region data loaded yet.')
    ).toBeInTheDocument();
    expect(screen.getByText('No data layers loaded yet.')).toBeInTheDocument();
    expect(screen.getByText('Traverse Planner & Profile')).toBeInTheDocument();
    expect(screen.getByText('No route planned')).toBeInTheDocument();
  });
});
