'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, Flag } from 'lucide-react';
import { FallbackWine } from '@/lib/types';
import { BugReportModal } from './BugReportModal';
import { useFeatureFlags } from '@/lib/feature-flags';

interface FallbackListProps {
  wines: FallbackWine[];
  onReset: () => void;
}

export function FallbackList({ wines, onReset }: FallbackListProps) {
  const t = useTranslations('fallback');
  const tBug = useTranslations('bugReport');
  const [showBugReport, setShowBugReport] = useState(false);
  const { bugReport: bugReportEnabled } = useFeatureFlags();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 py-6">
      <AlertTriangle className="w-10 h-10 text-yellow-400 mb-4" />
      <h2 className="text-lg font-semibold text-white mb-2">
        {t('couldNotIdentify')}
      </h2>
      <p className="text-gray-400 text-sm mb-8">
        {t('tryDifferentAngle')}
      </p>

      {/* Reset Button */}
      <button
        onClick={onReset}
        className="
          w-full bg-white text-black font-semibold py-4
          rounded-xl transition-all duration-200
          hover:bg-gray-100 active:scale-[0.98]
        "
      >
        {t('tryAnother')}
      </button>

      {bugReportEnabled && (
        <button
          onClick={() => setShowBugReport(true)}
          className="flex items-center justify-center gap-1.5 text-gray-500 hover:text-gray-400 text-xs mt-4 transition-colors"
        >
          <Flag className="w-3 h-3" />
          {tBug('notExpected')}
        </button>
      )}

      {/* Bug Report Modal */}
      <BugReportModal
        isOpen={showBugReport}
        onClose={() => setShowBugReport(false)}
        reportType="full_failure"
        metadata={{
          wines_detected: 0,
          wines_in_fallback: wines.length,
        }}
      />
    </div>
  );
}
