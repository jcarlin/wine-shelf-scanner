/**
 * Image conversion utilities for handling HEIC files
 * HEIC images are common from iPhones but not supported in most browsers
 */

import { Config } from './config';

/**
 * Detect if a file is HEIC format by checking MIME type and extension
 * Some browsers report wrong MIME type for HEIC, so we check both
 */
export function isHeicFile(file: File): boolean {
  const mimeType = file.type.toLowerCase();
  const fileName = file.name.toLowerCase();

  // Check MIME types (some browsers use different types for HEIC)
  const heicMimeTypes = ['image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence'];
  if (heicMimeTypes.includes(mimeType)) {
    return true;
  }

  // Check file extension (fallback when MIME type is empty or generic)
  const heicExtensions = ['.heic', '.heif'];
  return heicExtensions.some((ext) => fileName.endsWith(ext));
}

/**
 * Convert HEIC file to JPEG using backend /preview endpoint
 * This is more robust than browser-based heic2any which fails on some iPhone HEIC variants
 */
async function convertHeicViaBackend(file: File): Promise<Blob> {
  console.log('[HEIC] Converting via backend:', file.name, 'size:', file.size);

  const formData = new FormData();
  formData.append('image', file, file.name);

  const response = await fetch(`${Config.API_BASE_URL}/preview`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Backend preview failed: ${response.status}`);
  }

  const blob = await response.blob();
  console.log('[HEIC] Backend conversion successful, size:', blob.size);
  return blob;
}

/**
 * Convert HEIC file to JPEG blob
 * Tries backend first (more robust), falls back to heic2any
 */
export async function convertHeicToJpeg(file: File): Promise<Blob> {
  console.log('[HEIC] Converting file:', file.name, 'size:', file.size, 'type:', file.type);

  // Try backend conversion first (handles all HEIC variants)
  try {
    return await convertHeicViaBackend(file);
  } catch (backendErr) {
    console.warn('[HEIC] Backend conversion failed, trying heic2any:', backendErr);
  }

  // Fallback to heic2any (works offline, but fails on some HEIC variants)
  const heic2any = (await import('heic2any')).default;

  try {
    const result = await heic2any({
      blob: file,
      toType: 'image/jpeg',
      quality: 0.85,
    });

    console.log('[HEIC] heic2any conversion successful');

    if (Array.isArray(result)) {
      return result[0];
    }
    return result;
  } catch (err) {
    console.error('[HEIC] All conversion methods failed:', err);
    throw err;
  }
}

/**
 * Get a displayable image URL for a file
 * Converts HEIC to JPEG if needed, otherwise creates blob URL directly
 */
export async function getDisplayableImageUrl(file: File): Promise<string> {
  if (isHeicFile(file)) {
    const jpegBlob = await convertHeicToJpeg(file);
    return URL.createObjectURL(jpegBlob);
  }

  // Non-HEIC files can be displayed directly
  return URL.createObjectURL(file);
}
