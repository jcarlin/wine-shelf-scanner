'use client';

import { useState, useEffect } from 'react';
import { Wine } from 'lucide-react';
import { colors } from '@/lib/theme';

const tips = [
  'Tap any rating badge to see details',
  'Top-rated bottles get a gold highlight',
  'Powered by 21 million aggregated reviews',
  'We cover 181,000+ wines worldwide',
];

export function ProcessingSpinner() {
  const [tipIndex, setTipIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setTipIndex((prev) => (prev + 1) % tips.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-6">
      {/* Animated Wine Icon */}
      <div className="relative mb-8">
        <div
          className="w-24 h-24 rounded-full flex items-center justify-center animate-pulse"
          style={{ backgroundColor: colors.wine }}
        >
          <Wine className="w-12 h-12 text-white" />
        </div>
        {/* Spinning ring */}
        <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-star animate-spin" />
      </div>

      {/* Status Text */}
      <h2 className="text-xl font-semibold text-white mb-2">
        Analyzing wines...
      </h2>
      <p
        key={tipIndex}
        className="text-gray-400 text-center max-w-sm animate-fade-in"
      >
        {tips[tipIndex]}
      </p>

      {/* Progress indicator dots */}
      <div className="flex gap-2 mt-6">
        <div className="w-2 h-2 rounded-full bg-star animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="w-2 h-2 rounded-full bg-star animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="w-2 h-2 rounded-full bg-star animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  );
}
