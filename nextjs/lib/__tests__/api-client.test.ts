// Mock config before importing api-client
jest.mock('../config', () => ({
  Config: {
    API_BASE_URL: 'http://localhost:8000',
    REQUEST_TIMEOUT: 45000,
    IMAGE_QUALITY: 0.8,
    DEBUG_MODE: false,
    USE_MOCKS: false,
    MOCK_SCENARIO: 'full_shelf' as const,
  },
}));

// Mock fetch globally
const mockFetch = jest.fn();
(global as any).fetch = mockFetch;

// Reset modules before each test to get fresh imports
beforeEach(() => {
  jest.resetModules();
  mockFetch.mockReset();
});

describe('api-client', () => {
  describe('scanImage', () => {
    it('should make POST request to /scan endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          image_id: 'test-id',
          results: [],
          fallback_list: [],
        }),
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'photo.jpg', { type: 'image/jpeg' });
      await scanImage(file);

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, options] = mockFetch.mock.calls[0];
      expect(url).toContain('/scan');
      expect(options.method).toBe('POST');
    });

    it('should include image in FormData', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          image_id: 'test-id',
          results: [],
          fallback_list: [],
        }),
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'photo.jpg', { type: 'image/jpeg' });
      await scanImage(file);

      const [, options] = mockFetch.mock.calls[0];
      expect(options.body).toBeInstanceOf(FormData);
    });

    it('should return success with data on successful response', async () => {
      const mockResponse = {
        image_id: 'test-id',
        results: [
          {
            wine_name: 'Test Wine',
            rating: 4.5,
            confidence: 0.9,
            bbox: { x: 0.1, y: 0.2, width: 0.1, height: 0.3 },
          },
        ],
        fallback_list: [],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      const result = await scanImage(file);

      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(mockResponse);
      }
    });

    it('should return SERVER_ERROR on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      const result = await scanImage(file);

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.type).toBe('SERVER_ERROR');
        expect(result.error.status).toBe(500);
      }
    });

    it('should return NETWORK_ERROR on fetch failure', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network request failed'));

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      const result = await scanImage(file);

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.type).toBe('NETWORK_ERROR');
      }
    });

    it('should return TIMEOUT on abort', async () => {
      // Create an AbortError
      const abortError = new Error('Aborted');
      abortError.name = 'AbortError';
      mockFetch.mockRejectedValueOnce(abortError);

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      const result = await scanImage(file);

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.type).toBe('TIMEOUT');
      }
    });
  });

  describe('scanImage with debug option', () => {
    it('should append debug=true query param when debug option is true', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          image_id: 'test-id',
          results: [],
          fallback_list: [],
        }),
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      await scanImage(file, { debug: true });

      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('debug=true');
    });

    it('should not append debug param when debug option is false', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          image_id: 'test-id',
          results: [],
          fallback_list: [],
        }),
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      await scanImage(file, { debug: false });

      const [url] = mockFetch.mock.calls[0];
      expect(url).not.toContain('debug');
    });
  });

  describe('error types', () => {
    it('should have correct ApiError type structure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      const { scanImage } = require('../api-client');
      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      const result = await scanImage(file);

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error).toHaveProperty('type');
        expect(result.error).toHaveProperty('message');
        expect(['NETWORK_ERROR', 'SERVER_ERROR', 'TIMEOUT', 'PARSE_ERROR']).toContain(
          result.error.type
        );
      }
    });
  });

  describe('checkServerHealth', () => {
    it('returns healthy on 200', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
      });

      const { checkServerHealth } = require('../api-client');
      const result = await checkServerHealth();

      expect(result).toEqual({ status: 'healthy' });
    });

    it('returns warming_up with Retry-After on 503', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
        headers: { get: (name: string) => (name === 'Retry-After' ? '12' : null) },
      });

      const { checkServerHealth } = require('../api-client');
      const result = await checkServerHealth();

      expect(result).toEqual({ status: 'warming_up', retryAfter: 12 });
    });

    it('returns unavailable on other non-2xx responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
      });

      const { checkServerHealth } = require('../api-client');
      const result = await checkServerHealth();

      expect(result).toEqual({
        status: 'unavailable',
        message: 'Server returned 500',
      });
    });

    it('treats AbortError (timeout) as warming_up so polling continues during cold start', async () => {
      const abortError = new Error('Aborted');
      abortError.name = 'AbortError';
      mockFetch.mockRejectedValueOnce(abortError);

      const { checkServerHealth } = require('../api-client');
      const result = await checkServerHealth();

      expect(result).toEqual({ status: 'warming_up', retryAfter: 5 });
    });

    it('treats generic network errors as warming_up', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network request failed'));

      const { checkServerHealth } = require('../api-client');
      const result = await checkServerHealth();

      expect(result).toEqual({ status: 'warming_up', retryAfter: 5 });
    });
  });
});

describe('Config', () => {
  it('should have REQUEST_TIMEOUT of 45000ms', () => {
    const { Config } = require('../config');
    expect(Config.REQUEST_TIMEOUT).toBe(45000);
  });

  it('should have IMAGE_QUALITY between 0 and 1', () => {
    const { Config } = require('../config');
    expect(Config.IMAGE_QUALITY).toBeGreaterThan(0);
    expect(Config.IMAGE_QUALITY).toBeLessThanOrEqual(1);
  });

  it('should have DEBUG_MODE defined', () => {
    const { Config } = require('../config');
    expect(Config.DEBUG_MODE).toBeDefined();
  });

  it('should have USE_MOCKS defined', () => {
    const { Config } = require('../config');
    expect(Config.USE_MOCKS).toBeDefined();
  });

  it('should have MOCK_SCENARIO defined', () => {
    const { Config } = require('../config');
    expect(Config.MOCK_SCENARIO).toBeDefined();
    expect(['full_shelf', 'partial_detection', 'low_confidence', 'empty_results']).toContain(
      Config.MOCK_SCENARIO
    );
  });
});
