/**
 * Anonymous device ID for bug reports and feedback.
 * Generates a UUID and persists it in localStorage.
 */

const STORAGE_KEY = 'wine_scanner_device_id';

function generateUUID(): string {
  // Use crypto.randomUUID if available, otherwise fallback
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback UUID v4 generation
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function getDeviceId(): string {
  if (typeof window === 'undefined') {
    // SSR fallback — will be replaced on client
    return 'ssr-placeholder';
  }

  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;

    const newId = generateUUID();
    localStorage.setItem(STORAGE_KEY, newId);
    return newId;
  } catch {
    // localStorage unavailable (private browsing, etc.)
    return generateUUID();
  }
}
