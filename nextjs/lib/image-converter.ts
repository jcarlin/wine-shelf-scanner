/**
 * Image conversion utilities for handling HEIC files
 * HEIC images are common from iPhones but not supported in most browsers
 */

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
 * Convert HEIC file to JPEG blob
 * Uses dynamic import so heic2any (~400KB) only loads when needed
 */
export async function convertHeicToJpeg(file: File): Promise<Blob> {
  // Dynamic import - only load heic2any when actually converting
  const heic2any = (await import('heic2any')).default;

  const result = await heic2any({
    blob: file,
    toType: 'image/jpeg',
    quality: 0.85, // Visually lossless, smaller file size
  });

  // heic2any can return array if multiple: true, but we use single conversion
  if (Array.isArray(result)) {
    return result[0];
  }
  return result;
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
