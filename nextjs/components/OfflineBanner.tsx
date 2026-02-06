'use client';

import { WifiOff } from 'lucide-react';

/**
 * Persistent banner shown when the device is offline.
 * Matches the iOS OfflineBanner in ContentView.swift.
 */
export function OfflineBanner() {
  return (
    <div className="flex items-center justify-center gap-1.5 w-full py-1.5 bg-orange-500/80 text-white text-xs font-medium">
      <WifiOff className="w-3.5 h-3.5" />
      <span>Offline</span>
    </div>
  );
}
