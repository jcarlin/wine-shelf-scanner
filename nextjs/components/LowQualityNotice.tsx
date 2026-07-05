'use client';

import { useTranslations } from 'next-intl';
import { ZoomIn } from 'lucide-react';

interface LowQualityNoticeProps {
  onReset: () => void;
}

/**
 * Shown when the backend's input-quality gate rejects a scan: the bottles in
 * the photo are too small for label text to be legible. Explains the problem
 * and asks the user to move closer and retake — never a dead end.
 */
export function LowQualityNotice({ onReset }: LowQualityNoticeProps) {
  const t = useTranslations('fallback');

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 py-6">
      <ZoomIn className="w-10 h-10 text-yellow-400 mb-4" />
      <h2 className="text-lg font-semibold text-white mb-2">
        {t('tooFarTitle')}
      </h2>
      <p className="text-gray-400 text-sm mb-8 text-center max-w-xs">
        {t('tooFarMessage')}
      </p>

      <button
        onClick={onReset}
        className="
          w-full bg-white text-black font-semibold py-4
          rounded-xl transition-all duration-200
          hover:bg-gray-100 active:scale-[0.98]
        "
      >
        {t('retake')}
      </button>
    </div>
  );
}
