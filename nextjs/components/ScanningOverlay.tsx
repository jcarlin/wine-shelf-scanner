'use client';

import { useTranslations } from 'next-intl';
import { useTipRotation } from '@/hooks/useTipRotation';

const tipKeys = ['tip1', 'tip2', 'tip3', 'tip4'] as const;

interface ScanningOverlayProps {
  imageUri: string;
}

export function ScanningOverlay({ imageUri }: ScanningOverlayProps) {
  const t = useTranslations('processing');
  const tipIndex = useTipRotation(tipKeys.length);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4">
      <div className="relative w-full max-w-lg overflow-hidden rounded-xl">
        {/* Uploaded image — blob URL from camera/file upload, not compatible with next/image */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUri}
          alt="Scanning wine shelf"
          className="w-full h-auto object-contain"
        />

        {/* Scanner line with glow effect */}
        <div className="absolute left-0 right-0 h-1 animate-scan-line -translate-y-1/2">
          {/* Gradient glow above and below the line */}
          <div className="absolute -top-8 left-0 right-0 h-16 bg-gradient-to-b from-transparent via-star/30 to-transparent pointer-events-none" />
          {/* Core scanner line */}
          <div className="h-0.5 bg-star shadow-[0_0_10px_#FFCC00,0_0_20px_#FFCC00]" />
        </div>

        {/* Status text overlay at bottom */}
        <div className="absolute bottom-4 left-0 right-0 text-center">
          <div className="inline-block bg-black/60 backdrop-blur-sm px-4 py-2 rounded-lg">
            <span className="text-white font-medium">{t('analyzing')}</span>
          </div>
        </div>
      </div>

      {/* Rotating tip below the image */}
      <p
        key={tipIndex}
        className="text-gray-400 text-sm text-center mt-4 animate-fade-in"
      >
        {t(tipKeys[tipIndex])}
      </p>
    </div>
  );
}
