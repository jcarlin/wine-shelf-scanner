'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  CameraCapture,
  ProcessingSpinner,
  ScanningOverlay,
  ResultsView,
  BugReportModal,
  ServerWarmupOverlay,
  OfflineBanner,
  CachedScansView,
  CachedResultBanner,
} from '@/components';
import { useScanState } from '@/hooks/useScanState';
import { useServerHealth } from '@/hooks/useServerHealth';
import { useNetworkStatus } from '@/hooks/useNetworkStatus';
import { useFeatureFlags } from '@/lib/feature-flags';
import { Flag, Clock } from 'lucide-react';

export default function Home() {
  const { state, processImage, reset, scanCache, showCachedScan } = useScanState();
  const { state: serverState, retry: retryServerCheck } = useServerHealth();
  const { isOnline } = useNetworkStatus();
  const t = useTranslations('error');
  const tBug = useTranslations('bugReport');
  const { bugReport: bugReportEnabled, offlineCache: offlineCacheEnabled } = useFeatureFlags();
  const [showBugReport, setShowBugReport] = useState(false);
  const [showCachedScans, setShowCachedScans] = useState(false);

  // Show warmup overlay while server is not ready (skip if offline with cache)
  if (serverState.status !== 'ready' && isOnline) {
    return <ServerWarmupOverlay state={serverState} onRetry={retryServerCheck} />;
  }

  return (
    <main className="min-h-screen flex flex-col">
      {/* Offline banner */}
      {offlineCacheEnabled && !isOnline && <OfflineBanner />}

      {/* Cached scans browser */}
      {showCachedScans && (
        <CachedScansView
          entries={scanCache.loadAll()}
          onSelect={(index) => {
            showCachedScan(index);
            setShowCachedScans(false);
          }}
          onDelete={(index) => scanCache.deleteAt(index)}
          onClearAll={() => scanCache.clearAll()}
          onClose={() => setShowCachedScans(false)}
        />
      )}

      {!showCachedScans && state.status === 'idle' && (
        <>
          <CameraCapture onImageSelected={processImage} />
          {/* Recent scans button */}
          {offlineCacheEnabled && scanCache.hasCachedScans() && (
            <div className="flex justify-center pb-6">
              <button
                onClick={() => setShowCachedScans(true)}
                className="flex items-center gap-2 bg-white/10 text-white font-semibold py-3 px-6 rounded-xl hover:bg-white/20 transition-all"
              >
                <Clock className="w-4 h-4" />
                Recent Scans
              </button>
            </div>
          )}
        </>
      )}

      {!showCachedScans && state.status === 'processing' && (
        state.imageUri ? (
          <ScanningOverlay imageUri={state.imageUri} />
        ) : (
          <ProcessingSpinner />
        )
      )}

      {!showCachedScans && state.status === 'results' && (
        <ResultsView
          response={state.response}
          imageUri={state.imageUri}
          onReset={reset}
        />
      )}

      {!showCachedScans && state.status === 'cachedResults' && (
        <>
          <CachedResultBanner timestamp={state.timestamp} />
          {state.imageUri ? (
            <ResultsView
              response={state.response}
              imageUri={state.imageUri}
              onReset={reset}
            />
          ) : (
            <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
              <p className="text-gray-400 text-sm mb-4">
                {state.response.results.length} cached {state.response.results.length === 1 ? 'result' : 'results'}
              </p>
              <button
                onClick={reset}
                className="bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100"
              >
                New Scan
              </button>
            </div>
          )}
        </>
      )}

      {!showCachedScans && state.status === 'error' && (
        <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
          <p className="text-red-400 text-lg mb-6">{state.message}</p>
          <button
            onClick={reset}
            className="bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100"
          >
            {t('tryAgain')}
          </button>
          {/* View cached scans on error */}
          {offlineCacheEnabled && scanCache.hasCachedScans() && (
            <button
              onClick={() => setShowCachedScans(true)}
              className="mt-4 flex items-center gap-1.5 text-orange-400 hover:text-orange-300 text-sm transition-colors"
            >
              <Clock className="w-3.5 h-3.5" />
              View Recent Scans
            </button>
          )}
          {bugReportEnabled && (
            <button
              onClick={() => setShowBugReport(true)}
              className="mt-4 flex items-center gap-1.5 text-gray-500 hover:text-gray-300 text-sm transition-colors"
            >
              <Flag className="w-3.5 h-3.5" />
              {tBug('reportIssue')}
            </button>
          )}
          <BugReportModal
            isOpen={showBugReport}
            onClose={() => setShowBugReport(false)}
            reportType="error"
            errorMessage={state.message}
          />
        </div>
      )}
    </main>
  );
}
