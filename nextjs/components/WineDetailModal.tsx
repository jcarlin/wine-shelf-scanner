'use client';

import { X, Star } from 'lucide-react';
import { WineResult } from '@/lib/types';
import { colors, fontSize } from '@/lib/theme';
import { confidenceLabel } from '@/lib/overlay-math';

interface WineDetailModalProps {
  wine: WineResult | null;
  onClose: () => void;
}

/** Maps wine type to display color */
const wineTypeColors: Record<string, string> = {
  Red: '#8B0000',
  White: '#F5DEB3',
  Rosé: '#FFB6C1',
  Sparkling: '#FFD700',
  Dessert: '#DAA520',
  Fortified: '#8B4513',
};

/** Gets contrasting text color for wine type badge */
function getWineTypeTextColor(wineType: string): string {
  const darkTextTypes = ['White', 'Sparkling', 'Rosé'];
  return darkTextTypes.includes(wineType) ? '#333333' : '#FFFFFF';
}

/** Formats review count (e.g., 12500 -> "12.5K reviews") */
function formatReviewCount(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1).replace(/\.0$/, '')}K reviews`;
  }
  return `${count} reviews`;
}

export function WineDetailModal({ wine, onClose }: WineDetailModalProps) {
  if (!wine) return null;

  const label = confidenceLabel(wine.confidence);
  const hasMetadata = wine.wine_type || wine.brand || wine.region || wine.varietal || wine.blurb;
  const hasReviews = wine.review_count || (wine.review_snippets && wine.review_snippets.length > 0);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 animate-fade-in"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed bottom-0 left-0 right-0 z-50 animate-slide-up max-h-[85vh]">
        <div
          className="bg-white rounded-t-3xl px-6 pt-4 pb-8 max-w-lg mx-auto overflow-y-auto max-h-[85vh]"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Handle bar */}
          <div className="w-10 h-1 bg-gray-300 rounded-full mx-auto mb-4" />

          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-full hover:bg-gray-100 transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>

          {/* Content */}
          <div className="text-center pt-4">
            {/* Wine Type Badge */}
            {wine.wine_type && (
              <div
                className="inline-block px-3 py-1 rounded-lg mb-4"
                style={{
                  backgroundColor: wineTypeColors[wine.wine_type] || colors.wine,
                  color: getWineTypeTextColor(wine.wine_type),
                }}
              >
                <span className="text-xs font-semibold uppercase tracking-wider">
                  {wine.wine_type}
                </span>
              </div>
            )}

            {/* Wine Name */}
            <h2
              className="font-bold text-gray-900 mb-1 px-8"
              style={{ fontSize: fontSize.xl }}
            >
              {wine.wine_name}
            </h2>

            {/* Brand/Winery */}
            {wine.brand && (
              <p className="text-gray-500 italic mb-4">by {wine.brand}</p>
            )}

            {/* Rating */}
            <div className="flex items-center justify-center gap-3 mb-1">
              <Star
                className="w-10 h-10 fill-current"
                style={{ color: colors.star }}
              />
              <span
                className="font-bold text-gray-900"
                style={{ fontSize: fontSize.rating }}
              >
                {wine.rating?.toFixed(1) ?? '—'}
              </span>
            </div>

            {/* Review Count */}
            {wine.review_count && wine.review_count > 0 && (
              <p className="text-sm text-gray-500 mb-2">
                {formatReviewCount(wine.review_count)}
              </p>
            )}

            {/* Confidence Label */}
            <div
              className={`
                inline-block px-4 py-2 rounded-full text-sm font-medium mb-4
                ${wine.confidence >= 0.85
                  ? 'bg-green-100 text-green-700'
                  : 'bg-yellow-100 text-yellow-700'
                }
              `}
            >
              {label}
            </div>

            {/* Divider */}
            {(hasMetadata || hasReviews) && (
              <div className="w-4/5 h-px bg-gray-200 mx-auto my-4" />
            )}

            {/* Region & Varietal */}
            {(wine.region || wine.varietal) && (
              <div className="flex justify-center gap-8 mb-4">
                {wine.region && (
                  <div className="text-center">
                    <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">
                      Region
                    </p>
                    <p className="text-base text-gray-900 font-medium">
                      {wine.region}
                    </p>
                  </div>
                )}
                {wine.varietal && (
                  <div className="text-center">
                    <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">
                      Varietal
                    </p>
                    <p className="text-base text-gray-900 font-medium">
                      {wine.varietal}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Blurb/Description */}
            {wine.blurb && (
              <div className="bg-gray-50 rounded-lg p-4 my-4">
                <p className="text-gray-600 italic text-center leading-relaxed">
                  "{wine.blurb}"
                </p>
              </div>
            )}

            {/* Review Snippets */}
            {wine.review_snippets && wine.review_snippets.length > 0 && (
              <div className="mt-4 text-left">
                <p className="text-base font-semibold text-gray-900 mb-2">
                  What people say
                </p>
                {wine.review_snippets.map((snippet, index) => (
                  <div
                    key={index}
                    className="bg-gray-50 border-l-3 py-2 px-3 mb-2 rounded-sm"
                    style={{ borderLeftWidth: 3, borderLeftColor: colors.star }}
                  >
                    <p className="text-sm text-gray-500 italic leading-relaxed">
                      "{snippet}"
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
