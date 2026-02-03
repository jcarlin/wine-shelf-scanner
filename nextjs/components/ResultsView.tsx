'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowLeft } from 'lucide-react';
import { ScanResponse, WineResult, Rect, Size } from '@/lib/types';
import { OverlayContainer } from './OverlayContainer';
import { WineDetailModal } from './WineDetailModal';
import { Toast } from './Toast';
import { FallbackList } from './FallbackList';
import { getImageBounds } from '@/lib/image-bounds';
import { isVisible } from '@/lib/overlay-math';

interface ResultsViewProps {
  response: ScanResponse;
  imageUri: string;
  onReset: () => void;
}

export function ResultsView({ response, imageUri, onReset }: ResultsViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [selectedWine, setSelectedWine] = useState<WineResult | null>(null);
  const [imageBounds, setImageBounds] = useState<Rect | null>(null);
  const [imageSize, setImageSize] = useState<Size | null>(null);
  const [showPartialToast, setShowPartialToast] = useState(false);

  // Check if we should show partial detection toast
  const visibleCount = response.results.filter((w) => isVisible(w.confidence)).length;
  const hasPartialDetection = response.fallback_list.length > 0 && visibleCount > 0;

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
    console.log('[ResultsView] calculateBounds:', {
      imageSize,
      containerSize,
      bounds
    });
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

  // Recalculate bounds when image size changes
  useEffect(() => {
    calculateBounds();
  }, [calculateBounds]);

  // Handle window resize
  useEffect(() => {
    const handleResize = () => calculateBounds();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [calculateBounds]);

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
          <span>New Scan</span>
        </button>
        <div className="flex-1 text-center">
          <span className="text-gray-400 text-sm">
            {visibleCount} bottle{visibleCount !== 1 ? 's' : ''} found
          </span>
        </div>
        <div className="w-20" /> {/* Spacer for centering */}
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
          message="Some bottles couldn't be recognized"
          onDismiss={() => setShowPartialToast(false)}
        />
      )}

      {/* Wine Detail Modal */}
      <WineDetailModal
        wine={selectedWine}
        onClose={() => setSelectedWine(null)}
      />
    </div>
  );
}
