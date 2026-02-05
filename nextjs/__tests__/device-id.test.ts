import { getDeviceId } from '@/lib/device-id';

describe('getDeviceId', () => {
  const STORAGE_KEY = 'wine_scanner_device_id';

  beforeEach(() => {
    localStorage.clear();
  });

  it('generates a new ID when none exists', () => {
    const id = getDeviceId();
    expect(id).toBeTruthy();
    expect(id.length).toBeGreaterThan(0);
  });

  it('persists the ID in localStorage', () => {
    const id = getDeviceId();
    expect(localStorage.getItem(STORAGE_KEY)).toBe(id);
  });

  it('returns the same ID on subsequent calls', () => {
    const first = getDeviceId();
    const second = getDeviceId();
    expect(first).toBe(second);
  });

  it('returns existing ID from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'existing-id-123');
    const id = getDeviceId();
    expect(id).toBe('existing-id-123');
  });

  it('generates UUID-formatted IDs', () => {
    const id = getDeviceId();
    // UUID v4 format: 8-4-4-4-12 hex chars
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    expect(id).toMatch(uuidRegex);
  });
});
