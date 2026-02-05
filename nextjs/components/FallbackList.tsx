'use client';

import { useState } from 'react';
import { Star, AlertTriangle, Flag } from 'lucide-react';
import { FallbackWine } from '@/lib/types';
import { colors } from '@/lib/theme';
import { BugReportModal } from './BugReportModal';
import { useFeatureFlags } from '@/lib/feature-flags';

interface FallbackListProps {
  wines: FallbackWine[];
  onReset: () => void;
}

export function FallbackList({ wines, onReset }: FallbackListProps) {
  const [showBugReport, setShowBugReport] = useState(false);
  const { bugReport: bugReportEnabled } = useFeatureFlags();

  // Sort by rating descending
  const sortedWines = [...wines].sort((a, b) => b.rating - a.rating);

  return (
    <div className="flex flex-col min-h-[60vh] px-4 py-6">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="flex items-center justify-center gap-2 mb-2">
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
          <h2 className="text-lg font-semibold text-white">
            Could not identify bottles
          </h2>
        </div>
        <p className="text-gray-400 text-sm">
          Here are some popular wines you might be looking for
        </p>
      </div>

      {/* Wine List */}
      <div className="flex-1 space-y-2 mb-6">
        {sortedWines.map((wine) => (
          <div
            key={wine.wine_name}
            className="flex items-center justify-between bg-white/5 rounded-lg px-4 py-3"
          >
            <span className="text-white font-medium flex-1 mr-4">
              {wine.wine_name}
            </span>
            <div className="flex items-center gap-1">
              <Star
                className="w-4 h-4 fill-current"
                style={{ color: colors.star }}
              />
              <span className="text-white font-bold">
                {wine.rating.toFixed(1)}
              </span>
            </div>
          </div>
        ))}

        {bugReportEnabled && (
          <button
            onClick={() => setShowBugReport(true)}
            className="flex items-center justify-center gap-1.5 text-gray-500 hover:text-gray-300 text-xs mt-2 transition-colors w-full"
          >
            <Flag className="w-3 h-3" />
            Not what you expected? Report an issue
          </button>
        )}
      </div>

      {/* Reset Button */}
      <button
        onClick={onReset}
        className="
          w-full bg-white text-black font-semibold py-4
          rounded-xl transition-all duration-200
          hover:bg-gray-100 active:scale-[0.98]
        "
      >
        Try Another Photo
      </button>

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
