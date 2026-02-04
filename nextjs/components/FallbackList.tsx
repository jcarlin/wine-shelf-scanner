'use client';

import { useTranslations } from 'next-intl';
import { Star, AlertTriangle } from 'lucide-react';
import { FallbackWine } from '@/lib/types';
import { colors } from '@/lib/theme';

interface FallbackListProps {
  wines: FallbackWine[];
  onReset: () => void;
}

export function FallbackList({ wines, onReset }: FallbackListProps) {
  const t = useTranslations('fallback');
  // Sort by rating descending
  const sortedWines = [...wines].sort((a, b) => b.rating - a.rating);

  return (
    <div className="flex flex-col min-h-[60vh] px-4 py-6">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="flex items-center justify-center gap-2 mb-2">
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
          <h2 className="text-lg font-semibold text-white">
            {t('couldNotIdentify')}
          </h2>
        </div>
        <p className="text-gray-400 text-sm">
          {t('popularWines')}
        </p>
      </div>

      {/* Wine List */}
      <div className="flex-1 space-y-2 mb-6">
        {sortedWines.map((wine, index) => (
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
        {t('tryAnother')}
      </button>
    </div>
  );
}
