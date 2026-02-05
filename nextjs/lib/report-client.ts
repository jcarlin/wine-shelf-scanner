/**
 * Client for submitting bug reports to the backend /report endpoint.
 */

import { Config } from './config';
import { BugReportRequest, BugReportResponse, BugReportType, BugReportErrorType, BugReportMetadata } from './types';
import { getDeviceId } from './device-id';

interface SubmitReportOptions {
  reportType: BugReportType;
  errorType?: BugReportErrorType | null;
  errorMessage?: string | null;
  userDescription?: string | null;
  imageId?: string | null;
  metadata?: BugReportMetadata | null;
}

/**
 * Submit a bug report to the backend.
 * Fire-and-forget: resolves true on success, false on failure.
 * Never throws — errors are silently logged.
 */
export async function submitBugReport(options: SubmitReportOptions): Promise<boolean> {
  try {
    const payload: BugReportRequest = {
      report_type: options.reportType,
      error_type: options.errorType ?? null,
      error_message: options.errorMessage ?? null,
      user_description: options.userDescription?.slice(0, 500) ?? null,
      image_id: options.imageId ?? null,
      device_id: getDeviceId(),
      platform: 'web',
      app_version: getAppVersion(),
      timestamp: new Date().toISOString(),
      metadata: options.metadata ?? null,
    };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const response = await fetch(`${Config.API_BASE_URL}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      console.warn(`Bug report failed: ${response.status}`);
      return false;
    }

    const data: BugReportResponse = await response.json();
    return data.success;
  } catch (error) {
    console.warn('Bug report submission failed:', error);
    return false;
  }
}

function getAppVersion(): string | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../../package.json').version ?? null;
  } catch {
    return null;
  }
}

/**
 * Infer error type from an error message string.
 */
export function inferErrorType(message: string): BugReportErrorType | null {
  const lower = message.toLowerCase();
  if (lower.includes('network') || lower.includes('connect') || lower.includes('internet')) {
    return 'NETWORK_ERROR';
  }
  if (lower.includes('server') || lower.includes('returned')) {
    return 'SERVER_ERROR';
  }
  if (lower.includes('timeout') || lower.includes('timed out')) {
    return 'TIMEOUT';
  }
  if (lower.includes('parse') || lower.includes('unexpected')) {
    return 'PARSE_ERROR';
  }
  return null;
}
