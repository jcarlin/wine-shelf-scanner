'use client';

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowLeft, Share2, Star, Flag } from 'lucide-react';
import { ScanResponse, WineResult, Rect, Size } from '@/lib/types';
import { OverlayContainer } from './OverlayContainer';
import { WineDetailModal } from './WineDetailModal';
import { BugReportModal } from './BugReportModal';
import { Toast } from './Toast';
import { FallbackList } from './FallbackList';
import { getImageBounds } from '@/lib/image-bounds';
import { isVisible } from '@/lib/overlay-math';
import { useFeatureFlags } from '@/lib/feature-flags';
import { computeShelfRankings, TOP_WINES_COUNT } from '@/lib/shelf-rankings';
import { useWineReviews } from '@/hooks/useWineReviews';

interface ResultsViewProps {
  response: ScanResponse;
  imageUri: string;
  onReset: () => void;
}

export function ResultsView({ response, imageUri, onReset }: ResultsViewProps) {
  const t = useTranslations('results');
  const tBug = useTranslations('bugReport');
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [selectedWine, setSelectedWine] = useState<WineResult | null>(null);
  const [imageBounds, setImageBounds] = useState<Rect | null>(null);
  const [imageSize, setImageSize] = useState<Size | null>(null);
  const [showPartialToast, setShowPartialToast] = useState(() => {
    return response.fallback_list.length > 0 && response.results.filter((w) => isVisible(w.confidence)).length > 0;
  });
  const [showBugReport, setShowBugReport] = useState(false);
  const { shelfRanking, share: shareEnabled, bugReport: bugReportEnabled } = useFeatureFlags();

  // Prefetch reviews for all DB-matched wines as soon as results arrive
  const wineReviews = useWineReviews(response.results);

  // Check if we should show partial detection toast
  const visibleCount = response.results.filter((w) => isVisible(w.confidence)).length;
  const hasPartialDetection = response.fallback_list.length > 0 && visibleCount > 0;

  // Compute shelf rankings for wine detail modal
  const shelfRankings = useMemo(() => {
    if (!shelfRanking) return new Map<string, { rank: number; total: number }>();
    return computeShelfRankings(response.results);
  }, [shelfRanking, response.results]);

  // Get top wines (full objects) for header and sharing
  const topWines = useMemo(() => {
    return [...response.results]
      .filter((w) => isVisible(w.confidence) && w.rating !== null)
      .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
      .slice(0, TOP_WINES_COUNT);
  }, [response.results]);


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
          {topWines[0] ? (
            <span className="text-gray-300 text-sm flex items-center justify-center gap-1">
              <Star className="w-3.5 h-3.5 text-star fill-star" />
              <span className="font-medium text-white truncate max-w-[140px]">{topWines[0].wine_name}</span>
              <span className="text-gray-400">{t('more', { count: visibleCount - 1 })}</span>
            </span>
          ) : (
            <span className="text-gray-400 text-sm">
              {t('bottlesFound', { count: visibleCount })}
            </span>
          )}
        </div>
        <div className="w-20 flex justify-end">
          {shareEnabled && (
            <button
              onClick={() => {
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

      {/* Partial Detection Toast — disabled: we should never tell users
         "some bottles couldn't be recognized", just show what we found.
      {showPartialToast && (
        <div className="fixed bottom-24 left-1/2 transform -translate-x-1/2 flex items-center gap-3 z-40">
          <Toast
            message={t('partialDetection')}
            onDismiss={() => setShowPartialToast(false)}
          />
          {bugReportEnabled && (
            <button
              onClick={() => setShowBugReport(true)}
              className="flex items-center gap-1.5 text-yellow-400 text-sm font-semibold hover:text-yellow-300 transition-colors whitespace-nowrap underline underline-offset-2"
            >
              <Flag className="w-3.5 h-3.5" />
              {tBug('report')}
            </button>
          )}
        </div>
      )}
      */}

      {/* Wine Detail Modal */}
      <WineDetailModal
        wine={selectedWine}
        onClose={() => setSelectedWine(null)}
        shelfRank={selectedWine ? shelfRankings.get(selectedWine.wine_name)?.rank : undefined}
        shelfTotal={selectedWine ? shelfRankings.get(selectedWine.wine_name)?.total : undefined}
        fetchedReviews={selectedWine?.wine_id ? wineReviews.get(selectedWine.wine_id) : undefined}
      />

      {/* Bug Report Modal */}
      <BugReportModal
        isOpen={showBugReport}
        onClose={() => setShowBugReport(false)}
        reportType="partial_detection"
        imageId={response.image_id}
        metadata={{
          wines_detected: visibleCount,
          wines_in_fallback: response.fallback_list.length,
          confidence_scores: response.results.map((w) => w.confidence),
        }}
      />
    </div>
  );
}
