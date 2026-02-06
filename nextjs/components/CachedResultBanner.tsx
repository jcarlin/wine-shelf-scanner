'use client';

import { Clock } from 'lucide-react';

interface CachedResultBannerProps {
  timestamp: string; // ISO 8601
}

/**
 * Banner indicating results are from cache, with relative timestamp.
 * Matches the iOS CachedResultBanner in ContentView.swift.
 */
export function CachedResultBanner({ timestamp }: CachedResultBannerProps) {
  return (
    <div className="flex items-center justify-center gap-1.5 w-full py-1.5 bg-blue-500/70 text-white text-xs font-medium">
      <Clock className="w-3.5 h-3.5" />
      <span>Cached {formatRelativeTime(timestamp)}</span>
    </div>
  );
}

function formatRelativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;

  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  return `${days}d ago`;
}
