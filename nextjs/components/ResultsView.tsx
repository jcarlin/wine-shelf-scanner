'use client';

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowLeft, Share2 } from 'lucide-react';
import { ScanResponse, WineResult, Rect, Size } from '@/lib/types';
import { OverlayContainer } from './OverlayContainer';
import { WineDetailModal } from './WineDetailModal';
import { Toast } from './Toast';
import { FallbackList } from './FallbackList';
import { getImageBounds } from '@/lib/image-bounds';
import { isVisible } from '@/lib/overlay-math';
import { useFeatureFlags } from '@/lib/feature-flags';

interface ResultsViewProps {
  response: ScanResponse;
  imageUri: string;
  onReset: () => void;
}

export function ResultsView({ response, imageUri, onReset }: ResultsViewProps) {
  const t = useTranslations('results');
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [selectedWine, setSelectedWine] = useState<WineResult | null>(null);
  const [imageBounds, setImageBounds] = useState<Rect | null>(null);
  const [imageSize, setImageSize] = useState<Size | null>(null);
  const [showPartialToast, setShowPartialToast] = useState(false);
  const { shelfRanking, share: shareEnabled } = useFeatureFlags();

  // Check if we should show partial detection toast
  const visibleCount = response.results.filter((w) => isVisible(w.confidence)).length;
  const hasPartialDetection = response.fallback_list.length > 0 && visibleCount > 0;

  // Compute shelf rankings for wine detail modal
  const shelfRankings = useMemo(() => {
    if (!shelfRanking) return new Map<string, { rank: number; total: number }>();
    const visibleWines = response.results.filter((w) => isVisible(w.confidence));
    const ranked = [...visibleWines]
      .filter((w) => w.rating !== null)
      .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
    if (ranked.length < 3) return new Map<string, { rank: number; total: number }>();
    const rankings = new Map<string, { rank: number; total: number }>();
    let currentRank = 1;
    ranked.forEach((wine, index) => {
      if (index > 0 && wine.rating !== ranked[index - 1].rating) {
        currentRank = index + 1;
      }
      rankings.set(wine.wine_name, { rank: currentRank, total: ranked.length });
    });
    return rankings;
  }, [shelfRanking, response.results]);

  // Show toast on mount if partial detection
  useEffect(() => {
    if (hasPartialDetection) {
      setShowPartialToast(true);
    }
  }, [hasPartialDetection]);

  // Calculate image bounds when image loads or container resizes
  const calculateBounds = useCallback(() => {
    if (!containerRef.current || !imageSize) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const containerSize: Size = {
      width: containerRect.width,
      height: containerRect.height,
    };

    const bounds = getImageBounds(imageSize, containerSize);
    setImageBounds(bounds);
  }, [imageSize]);

  // Handle image load
  const handleImageLoad = () => {
    if (imageRef.current) {
      setImageSize({
        width: imageRef.current.naturalWidth,
        height: imageRef.current.naturalHeight,
      });
    }
  };

  // Use ResizeObserver for reliable container size tracking (handles iOS Safari viewport changes)
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver(() => {
      // Use requestAnimationFrame to ensure layout is complete
      requestAnimationFrame(() => {
        calculateBounds();
      });
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [calculateBounds]);

  // Also recalculate when image size becomes available
  useEffect(() => {
    if (imageSize) {
      // Wait for next frame to ensure container has final dimensions
      requestAnimationFrame(() => {
        calculateBounds();
      });
    }
  }, [imageSize, calculateBounds]);

  // If no visible results, show fallback list
  if (visibleCount === 0) {
    return <FallbackList wines={response.fallback_list} onReset={onReset} />;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center px-4 py-3 border-b border-gray-700">
        <button
          onClick={onReset}
          className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>{t('newScan')}</span>
        </button>
        <div className="flex-1 text-center">
          <span className="text-gray-400 text-sm">
            {t('bottlesFound', { count: visibleCount })}
          </span>
        </div>
        <div className="w-20 flex justify-end">
          {shareEnabled && (
            <button
              onClick={() => {
                const topWines = [...response.results]
                  .filter((w) => isVisible(w.confidence) && w.rating !== null)
                  .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
                  .slice(0, 3);
                const text = [
                  t('topPicks'),
                  ...topWines.map((w, i) => `${i + 1}. ${w.wine_name} - ${w.rating?.toFixed(1)} ${t('stars')}`),
                  '',
                  t('scannedWith'),
                ].join('\n');
                if (navigator.share) {
                  navigator.share({ text }).catch(() => {});
                } else {
                  navigator.clipboard.writeText(text).catch(() => {});
                }
              }}
              className="text-white hover:text-gray-300 transition-colors p-1"
            >
              <Share2 className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Image Container */}
      <div
        ref={containerRef}
        className="flex-1 relative overflow-hidden bg-black"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imageRef}
          src={imageUri}
          alt="Scanned wine shelf"
          onLoad={handleImageLoad}
          className="w-full h-full object-contain"
        />

        {/* Overlays */}
        {imageBounds && (
          <OverlayContainer
            wines={response.results}
            imageBounds={imageBounds}
            onWineSelect={setSelectedWine}
          />
        )}
      </div>

      {/* Partial Detection Toast */}
      {showPartialToast && (
        <Toast
          message={t('partialDetection')}
          onDismiss={() => setShowPartialToast(false)}
        />
      )}

      {/* Wine Detail Modal */}
      <WineDetailModal
        wine={selectedWine}
        onClose={() => setSelectedWine(null)}
        shelfRank={selectedWine ? shelfRankings.get(selectedWine.wine_name)?.rank : undefined}
        shelfTotal={selectedWine ? shelfRankings.get(selectedWine.wine_name)?.total : undefined}
      />
    </div>
  );
}
