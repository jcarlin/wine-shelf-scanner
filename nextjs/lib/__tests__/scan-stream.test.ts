/**
 * scanImageStream — progressive scan via SSE over fetch.
 *
 * Contract with the backend (POST /scan/stream):
 *  - `partial` events: complete ScanResponse (cumulative replacement)
 *  - `done` event: final ScanResponse (same as POST /scan)
 *  - `error` event: {message} — pipeline failed after streaming began
 * Client policy:
 *  - onPartial fires for each partial
 *  - non-OK response (404/501/…) or network error before any event →
 *    fall back to plain POST /scan
 *  - error event / stream cut AFTER partials arrived → resolve with the
 *    last partial (never throw away rendered badges)
 *  - error event with NO partials → SERVER_ERROR failure
 */

export {}; // make this file a module so mockFetch doesn't clash with api-client.test.ts

jest.mock('../config', () => ({
  Config: {
    API_BASE_URL: 'http://localhost:8000',
    REQUEST_TIMEOUT: 45000,
    DEBUG_MODE: false,
    USE_MOCKS: false,
    MOCK_SCENARIO: 'full_shelf' as const,
  },
}));

const mockFetch = jest.fn();
(global as any).fetch = mockFetch;

beforeEach(() => {
  jest.resetModules();
  mockFetch.mockReset();
});

function sseBody(events: Array<{ event: string; data: unknown }>) {
  const encoder = new TextEncoder();
  const chunks = events.map(({ event, data }) =>
    encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  );
  let i = 0;
  return {
    getReader: () => ({
      read: async () =>
        i < chunks.length
          ? { done: false, value: chunks[i++] }
          : { done: true, value: undefined },
      releaseLock: () => {},
      cancel: async () => {},
    }),
  };
}

const partialResponse = {
  image_id: 'id-1',
  results: [
    { wine_name: 'Opus One', rating: 4.6, confidence: 0.9,
      bbox: { x: 0.1, y: 0.1, width: 0.1, height: 0.4 } },
  ],
  fallback_list: [],
};

const doneResponse = {
  image_id: 'id-1',
  results: [
    ...partialResponse.results,
    { wine_name: 'Caymus Cabernet Sauvignon', rating: 4.4, confidence: 0.88,
      bbox: { x: 0.3, y: 0.1, width: 0.1, height: 0.4 } },
  ],
  fallback_list: [],
};

describe('scanImageStream', () => {
  it('fires onPartial per partial event and resolves with the done response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: sseBody([
        { event: 'partial', data: partialResponse },
        { event: 'done', data: doneResponse },
      ]),
    });

    const { scanImageStream } = require('../api-client');
    const file = new File(['x'], 'shelf.jpg', { type: 'image/jpeg' });
    const onPartial = jest.fn();

    const result = await scanImageStream(file, { onPartial });

    expect(onPartial).toHaveBeenCalledTimes(1);
    expect(onPartial.mock.calls[0][0].results).toHaveLength(1);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.results).toHaveLength(2);
    }
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/scan/stream');
  });

  it('falls back to POST /scan when the stream endpoint is unavailable', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: false, status: 501 })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => doneResponse,
      });

    const { scanImageStream } = require('../api-client');
    const file = new File(['x'], 'shelf.jpg', { type: 'image/jpeg' });

    const result = await scanImageStream(file, { onPartial: jest.fn() });

    expect(result.success).toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const [fallbackUrl] = mockFetch.mock.calls[1];
    expect(fallbackUrl).toContain('/scan');
    expect(fallbackUrl).not.toContain('/scan/stream');
  });

  it('resolves with the last partial when an error event follows partials', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: sseBody([
        { event: 'partial', data: partialResponse },
        { event: 'error', data: { message: 'Scan failed. Please try again.' } },
      ]),
    });

    const { scanImageStream } = require('../api-client');
    const file = new File(['x'], 'shelf.jpg', { type: 'image/jpeg' });

    const result = await scanImageStream(file, { onPartial: jest.fn() });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.results).toHaveLength(1);
    }
    expect(mockFetch).toHaveBeenCalledTimes(1); // no double-spend fallback
  });

  it('returns SERVER_ERROR when the error event arrives before any partial', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: sseBody([
        { event: 'error', data: { message: 'Scan failed. Please try again.' } },
      ]),
    });

    const { scanImageStream } = require('../api-client');
    const file = new File(['x'], 'shelf.jpg', { type: 'image/jpeg' });

    const result = await scanImageStream(file, { onPartial: jest.fn() });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.type).toBe('SERVER_ERROR');
    }
  });
});
