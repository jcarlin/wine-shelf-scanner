'use client';

import { useState, useEffect } from 'react';
import { Clock, Trash2, X, Star } from 'lucide-react';
import { CachedScan } from '@/hooks/useScanCache';
import { colors } from '@/lib/theme';

interface CachedScansViewProps {
  entries: CachedScan[];
  onSelect: (index: number) => void;
  onDelete: (index: number) => void;
  onClearAll: () => void;
  onClose: () => void;
}

/**
 * Browse previously cached scan results.
 * Matches the iOS CachedScansView.swift pattern.
 */
export function CachedScansView({
  entries,
  onSelect,
  onDelete,
  onClearAll,
  onClose,
}: CachedScansViewProps) {
  // Re-render when entries change (after delete)
  const [localEntries, setLocalEntries] = useState(entries);
  useEffect(() => { setLocalEntries(entries); }, [entries]);

  const handleDelete = (index: number) => {
    onDelete(index);
    setLocalEntries((prev) => prev.filter((_, i) => i !== index));
  };

  if (localEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] px-6 text-center">
        <Clock className="w-12 h-12 text-gray-600 mb-4" />
        <p className="text-gray-400 text-lg mb-2">No recent scans</p>
        <p className="text-gray-500 text-sm mb-6">Scan results are cached here for offline access</p>
        <button
          onClick={onClose}
          className="bg-white/20 text-white font-semibold py-3 px-8 rounded-xl hover:bg-white/30"
        >
          Back
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-[40vh] px-4 py-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Recent Scans</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              onClearAll();
              setLocalEntries([]);
            }}
            className="text-red-400 hover:text-red-300 text-xs transition-colors"
          >
            Clear All
          </button>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors p-1"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Scan list */}
      <div className="space-y-2">
        {localEntries.map((entry, index) => {
          const topWine = entry.response.results
            .filter((w) => w.rating !== null)
            .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))[0];
          const wineCount = entry.response.results.length;

          return (
            <div
              key={`${entry.timestamp}-${index}`}
              className="flex items-center gap-3 bg-white/5 rounded-lg p-3 hover:bg-white/10 transition-colors cursor-pointer group"
              onClick={() => onSelect(index)}
            >
              {/* Thumbnail */}
              {entry.imageUri ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={entry.imageUri}
                  alt="Scan thumbnail"
                  className="w-14 h-14 rounded-md object-cover flex-shrink-0"
                />
              ) : (
                <div className="w-14 h-14 rounded-md bg-white/10 flex items-center justify-center flex-shrink-0">
                  <Clock className="w-6 h-6 text-gray-500" />
                </div>
              )}

              {/* Info */}
              <div className="flex-1 min-w-0">
                {topWine && (
                  <div className="flex items-center gap-1 mb-0.5">
                    <Star className="w-3 h-3 fill-current flex-shrink-0" style={{ color: colors.star }} />
                    <span className="text-white text-sm font-medium truncate">
                      {topWine.wine_name}
                    </span>
                  </div>
                )}
                <p className="text-gray-500 text-xs">
                  {wineCount} {wineCount === 1 ? 'bottle' : 'bottles'} &middot; {formatRelativeTime(entry.timestamp)}
                </p>
              </div>

              {/* Delete button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(index);
                }}
                className="text-gray-600 hover:text-red-400 transition-colors p-1.5 opacity-0 group-hover:opacity-100"
                aria-label="Delete scan"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
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
