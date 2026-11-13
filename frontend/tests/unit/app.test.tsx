import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import App from '../../src/App';

// Mock Leaflet MapContainer since jsdom does not support full DOM layout
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children, crs }: { children: React.ReactNode; crs: unknown }) => (
    <div data-testid="leaflet-map" data-crs={String(crs)}>
      {children}
    </div>
  ),
}));

describe('App Layout Shell (WP-04)', () => {
  it('renders Mission Control header and indicators', () => {
    render(<App />);

    expect(screen.getByText('MARSWALK')).toBeInTheDocument();
    expect(screen.getByText('Human-EVA Mission Control')).toBeInTheDocument();
    expect(screen.getByTestId('health-indicator')).toBeInTheDocument();
    expect(screen.getByTestId('llm-indicator')).toBeInTheDocument();
    expect(screen.getByTestId('leaflet-map')).toBeInTheDocument();
  });

  it('renders side panels and bottom drawer placeholders', () => {
    render(<App />);

    expect(screen.getByText('Layers & Products')).toBeInTheDocument();
    expect(screen.getByText('Inspector & Evidence')).toBeInTheDocument();
    expect(screen.getByText('Traverse Planner & Profile')).toBeInTheDocument();
  });
});
