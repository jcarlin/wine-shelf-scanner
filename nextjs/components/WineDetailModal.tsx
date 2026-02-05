'use client';

import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { X, Star, Share2 } from 'lucide-react';
import { WineResult } from '@/lib/types';
import { colors, fontSize } from '@/lib/theme';
import { HIGH_CONFIDENCE_THRESHOLD } from '@/lib/overlay-math';
import { useFeatureFlags } from '@/lib/feature-flags';
import { useWineMemory } from '@/hooks/useWineMemory';

interface WineDetailModalProps {
  wine: WineResult | null;
  onClose: () => void;
  shelfRank?: number;
  shelfTotal?: number;
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

/** Formats review count number for i18n (e.g., 12500 -> "12.5") */
function formatReviewCountNumber(count: number): string {
  return (count / 1000).toFixed(1).replace(/\.0$/, '');
}

export function WineDetailModal({ wine, onClose, shelfRank, shelfTotal }: WineDetailModalProps) {
  const t = useTranslations('detail');
  const flags = useFeatureFlags();
  const memory = useWineMemory();
  const [feedbackGiven, setFeedbackGiven] = useState(false);

  if (!wine) return null;

  const existingSentiment = flags.wineMemory ? memory.get(wine.wine_name) : undefined;

  const label = wine.confidence >= HIGH_CONFIDENCE_THRESHOLD ? t('widelyRated') : t('limitedData');
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
              <p className="text-gray-500 italic mb-4">{t('by', { brand: wine.brand })}</p>
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
                {wine.review_count >= 1000
                  ? t('reviewsK', { count: formatReviewCountNumber(wine.review_count) })
                  : t('reviews', { count: wine.review_count })}
              </p>
            )}

            {/* Trust Signals - Rating Sources */}
            {flags.trustSignals && wine.rating_sources && wine.rating_sources.length > 0 ? (
              <div className="inline-flex flex-col gap-1 px-4 py-2 rounded-xl mb-4"
                style={{ backgroundColor: 'rgba(59, 130, 246, 0.08)' }}
              >
                {wine.rating_sources.map((source, i) => (
                  <div key={i} className="flex items-center gap-1 text-xs">
                    <span className="text-gray-500 font-medium">{source.display_name}</span>
                    <span className="text-gray-900 font-semibold">
                      {Math.round(source.original_rating)} {source.scale_label}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
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
            )}

            {/* Safe Pick Badge */}
            {flags.safePick && wine.is_safe_pick && (
              <div className="inline-flex items-center gap-1 px-3 py-1 rounded-lg mb-2"
                style={{ backgroundColor: '#E8F5E9' }}
              >
                <span className="text-sm font-semibold" style={{ color: '#2E7D32' }}>
                  &#x2713; {t('crowdFavorite')}
                </span>
              </div>
            )}

            {/* Shelf Ranking */}
            {flags.shelfRanking && shelfRank !== undefined && shelfTotal !== undefined && (
              <p className={`text-sm mb-2 ${shelfRank === 1 ? 'font-semibold' : 'font-medium text-gray-500'}`}
                style={shelfRank === 1 ? { color: '#D4A017' } : undefined}
              >
                {shelfRank === 1 ? t('bestOnShelf') : t('rankedOnShelf', { rank: shelfRank, total: shelfTotal })}
              </p>
            )}

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
                      {t('region')}
                    </p>
                    <p className="text-base text-gray-900 font-medium">
                      {wine.region}
                    </p>
                  </div>
                )}
                {wine.varietal && (
                  <div className="text-center">
                    <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">
                      {t('varietal')}
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
                  &ldquo;{wine.blurb}&rdquo;
                </p>
              </div>
            )}

            {/* Food Pairing */}
            {flags.pairings && wine.pairing && (
              <div className="rounded-lg p-4 my-2 w-full" style={{ backgroundColor: '#FBF8F0' }}>
                <p className="text-sm text-gray-500 mb-1">&#x1F374; {t('goesWith')}</p>
                <p className="text-base text-gray-900 font-medium">{wine.pairing}</p>
              </div>
            )}

            {/* Wine Memory Banner */}
            {flags.wineMemory && existingSentiment && !feedbackGiven && (
              <div
                className="flex items-center justify-between w-full px-3 py-2 rounded-lg mb-2"
                style={{ backgroundColor: existingSentiment === 'liked' ? '#E8F5E9' : '#FFEBEE' }}
              >
                <span className="text-sm text-gray-600">
                  {existingSentiment === 'liked' ? `\u2665 ${t('youLiked')}` : `\u2715 ${t('youDisliked')}`}
                </span>
                <button
                  className="text-sm text-blue-500 font-medium hover:text-blue-600"
                  onClick={() => memory.clear(wine.wine_name)}
                >
                  {t('undo')}
                </button>
              </div>
            )}

            {/* Share Button */}
            {flags.share && (
              <button
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-blue-600 hover:bg-blue-50 transition-colors mb-2"
                style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)' }}
                onClick={() => {
                  const text = [
                    wine.wine_name,
                    wine.rating ? `${wine.rating.toFixed(1)}` : null,
                    wine.brand ? t('by', { brand: wine.brand }) : null,
                    wine.region ? `(${wine.region})` : null,
                    '',
                    t('foundWith'),
                  ].filter(Boolean).join(' ');

                  if (navigator.share) {
                    navigator.share({ text }).catch(() => {});
                  } else {
                    navigator.clipboard.writeText(text).catch(() => {});
                  }
                }}
              >
                <Share2 className="w-4 h-4" />
                {t('shareThisPick')}
              </button>
            )}

            {/* Feedback Section */}
            {flags.wineMemory && (
              <div className="py-2 text-center">
                {feedbackGiven ? (
                  <p className="text-sm font-medium" style={{ color: '#4CAF50' }}>
                    &#x2713; {t('thanksFeedback')}
                  </p>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <p className="text-sm text-gray-500">{t('isThisRight')}</p>
                    <div className="flex gap-8">
                      <button
                        className="flex flex-col items-center gap-1 hover:scale-110 transition-transform"
                        onClick={() => {
                          memory.save(wine.wine_name, 'liked');
                          setFeedbackGiven(true);
                        }}
                      >
                        <span className="text-2xl">&#x1F44D;</span>
                        <span className="text-xs text-gray-500">{t('yes')}</span>
                      </button>
                      <button
                        className="flex flex-col items-center gap-1 hover:scale-110 transition-transform"
                        onClick={() => {
                          memory.save(wine.wine_name, 'disliked');
                          setFeedbackGiven(true);
                        }}
                      >
                        <span className="text-2xl">&#x1F44E;</span>
                        <span className="text-xs text-gray-500">{t('no')}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Review Snippets */}
            {wine.review_snippets && wine.review_snippets.length > 0 && (
              <div className="mt-4 text-left">
                <p className="text-base font-semibold text-gray-900 mb-2">
                  {t('whatPeopleSay')}
                </p>
                {wine.review_snippets.map((snippet, index) => (
                  <div
                    key={index}
                    className="bg-gray-50 border-l-3 py-2 px-3 mb-2 rounded-sm"
                    style={{ borderLeftWidth: 3, borderLeftColor: colors.star }}
                  >
                    <p className="text-sm text-gray-500 italic leading-relaxed">
                      &ldquo;{snippet}&rdquo;
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
