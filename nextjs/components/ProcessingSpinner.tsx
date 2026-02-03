'use client';

import { Wine } from 'lucide-react';
import { colors } from '@/lib/theme';

export function ProcessingSpinner() {
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
      <p className="text-gray-400 text-center max-w-sm">
        Our AI is identifying bottles and fetching ratings. This may take a few seconds.
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
