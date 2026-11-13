import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ApiClient, ApiError } from '../../src/services/apiClient';

describe('ApiClient (T-FE-02)', () => {
  let client: ApiClient;

  beforeEach(() => {
    client = new ApiClient('/api/v1');
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('parses error envelope and surfaces error_code and message on 422', async () => {
    const errorPayload = {
      error_code: 'POINT_OUTSIDE_REGION',
      message: 'The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp.',
      details: { region_id: 'gale_mount_sharp' },
      request_id: 'req_3f2a9c1b',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => errorPayload,
    } as unknown as Response);

    try {
      await client.get('/terrain/point?region_id=gale&lat=-5.3&lon=137.9');
      expect.fail('Expected ApiError to be thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.errorCode).toBe('POINT_OUTSIDE_REGION');
      expect(apiErr.message).toBe(
        'The point (lat -5.3, lon 137.9) is outside region gale_mount_sharp.'
      );
      expect(apiErr.details).toEqual({ region_id: 'gale_mount_sharp' });
      expect(apiErr.requestId).toBe('req_3f2a9c1b');
    }
  });

  it('parses 404 error envelope and surfaces error_code and message', async () => {
    const errorPayload = {
      error_code: 'REGION_NOT_FOUND',
      message: "Region 'unknown_region' was not found.",
      details: { region_id: 'unknown_region' },
      request_id: 'req_123456',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => errorPayload,
    } as unknown as Response);

    await expect(client.get('/regions/unknown_region')).rejects.toThrow(
      "Region 'unknown_region' was not found."
    );

    try {
      await client.get('/regions/unknown_region');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.errorCode).toBe('REGION_NOT_FOUND');
      expect(apiErr.status).toBe(404);
    }
  });

  it('handles non-JSON error responses gracefully', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      json: async () => {
        throw new Error('Not JSON');
      },
    } as unknown as Response);

    try {
      await client.get('/health');
      expect.fail('Expected ApiError to be thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(502);
      expect(apiErr.errorCode).toBe('INTERNAL_ERROR');
      expect(apiErr.message).toContain('HTTP error 502: Bad Gateway');
    }
  });

  it('successfully returns data on 200 response', async () => {
    const healthData = {
      status: 'ok',
      version: '0.1.0',
      llm_mode: 'DISABLED',
      llm_provider: null,
      regions_loaded: 0,
      datasets_available: 0,
      datasets_unavailable: 0,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => healthData,
    } as unknown as Response);

    const result = await client.getHealth();
    expect(result).toEqual(healthData);
    expect(result.status).toBe('ok');
    expect(result.llm_mode).toBe('DISABLED');
  });
});
