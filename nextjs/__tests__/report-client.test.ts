import { submitBugReport, inferErrorType } from '@/lib/report-client';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock device-id
jest.mock('@/lib/device-id', () => ({
  getDeviceId: () => 'test-device-id-123',
}));

// Mock config
jest.mock('@/lib/config', () => ({
  Config: {
    API_BASE_URL: 'https://test-api.example.com',
  },
}));

describe('submitBugReport', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('sends POST request to /report endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, report_id: 'rpt-123' }),
    });

    await submitBugReport({
      reportType: 'error',
      errorMessage: 'Network error',
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe('https://test-api.example.com/report');
    expect(options.method).toBe('POST');
    expect(options.headers['Content-Type']).toBe('application/json');
  });

  it('includes required fields in payload', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, report_id: 'rpt-123' }),
    });

    await submitBugReport({
      reportType: 'error',
      errorType: 'NETWORK_ERROR',
      errorMessage: 'Connection failed',
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.report_type).toBe('error');
    expect(body.error_type).toBe('NETWORK_ERROR');
    expect(body.error_message).toBe('Connection failed');
    expect(body.device_id).toBe('test-device-id-123');
    expect(body.platform).toBe('web');
    expect(body.timestamp).toBeTruthy();
  });

  it('includes metadata when provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, report_id: 'rpt-123' }),
    });

    await submitBugReport({
      reportType: 'partial_detection',
      imageId: 'img-abc',
      metadata: {
        wines_detected: 2,
        wines_in_fallback: 5,
        confidence_scores: [0.85, 0.72],
      },
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.report_type).toBe('partial_detection');
    expect(body.image_id).toBe('img-abc');
    expect(body.metadata.wines_detected).toBe(2);
    expect(body.metadata.wines_in_fallback).toBe(5);
    expect(body.metadata.confidence_scores).toEqual([0.85, 0.72]);
  });

  it('truncates user description to 500 chars', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, report_id: 'rpt-123' }),
    });

    const longDescription = 'x'.repeat(600);
    await submitBugReport({
      reportType: 'error',
      userDescription: longDescription,
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.user_description.length).toBe(500);
  });

  it('returns true on success', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, report_id: 'rpt-123' }),
    });

    const result = await submitBugReport({ reportType: 'error' });
    expect(result).toBe(true);
  });

  it('returns false on server error (never throws)', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });

    const result = await submitBugReport({ reportType: 'error' });
    expect(result).toBe(false);
  });

  it('returns false on network error (never throws)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network failure'));

    const result = await submitBugReport({ reportType: 'error' });
    expect(result).toBe(false);
  });

  it('sends null for omitted optional fields', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, report_id: 'rpt-123' }),
    });

    await submitBugReport({ reportType: 'full_failure' });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.error_type).toBeNull();
    expect(body.error_message).toBeNull();
    expect(body.user_description).toBeNull();
    expect(body.image_id).toBeNull();
    expect(body.metadata).toBeNull();
  });
});

describe('inferErrorType', () => {
  it('detects network errors', () => {
    expect(inferErrorType('Unable to connect. Please check your internet connection.')).toBe('NETWORK_ERROR');
    expect(inferErrorType('Network error occurred')).toBe('NETWORK_ERROR');
  });

  it('detects server errors', () => {
    expect(inferErrorType('Server returned 500')).toBe('SERVER_ERROR');
  });

  it('detects timeout errors', () => {
    expect(inferErrorType('Request timed out. Please try again.')).toBe('TIMEOUT');
    expect(inferErrorType('Timeout exceeded')).toBe('TIMEOUT');
  });

  it('detects parse errors', () => {
    expect(inferErrorType('An unexpected error occurred.')).toBe('PARSE_ERROR');
    expect(inferErrorType('Failed to parse response')).toBe('PARSE_ERROR');
  });

  it('returns null for unknown error messages', () => {
    expect(inferErrorType('Something went wrong')).toBeNull();
  });
});
