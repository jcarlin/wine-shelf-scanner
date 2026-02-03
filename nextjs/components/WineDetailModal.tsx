'use client';

import { X, Star } from 'lucide-react';
import { WineResult } from '@/lib/types';
import { colors, fontSize } from '@/lib/theme';
import { confidenceLabel } from '@/lib/overlay-math';

interface WineDetailModalProps {
  wine: WineResult | null;
  onClose: () => void;
}

export function WineDetailModal({ wine, onClose }: WineDetailModalProps) {
  if (!wine) return null;

  const label = confidenceLabel(wine.confidence);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 animate-fade-in"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed bottom-0 left-0 right-0 z-50 animate-slide-up">
        <div
          className="bg-white rounded-t-3xl px-6 pt-4 pb-8 max-w-lg mx-auto"
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
            {/* Wine Name */}
            <h2
              className="font-bold text-gray-900 mb-4 px-8"
              style={{ fontSize: fontSize.xl }}
            >
              {wine.wine_name}
            </h2>

            {/* Rating */}
            <div className="flex items-center justify-center gap-3 mb-4">
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

            {/* Confidence Label */}
            <div
              className={`
                inline-block px-4 py-2 rounded-full text-sm font-medium
                ${wine.confidence >= 0.85
                  ? 'bg-green-100 text-green-700'
                  : 'bg-yellow-100 text-yellow-700'
                }
              `}
            >
              {label}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
