'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { CameraCapture, ProcessingSpinner, ScanningOverlay, ResultsView, BugReportModal, ServerWarmupOverlay } from '@/components';
import { useScanState } from '@/hooks/useScanState';
import { useServerHealth } from '@/hooks/useServerHealth';
import { useFeatureFlags } from '@/lib/feature-flags';
import { Flag, Wrench } from 'lucide-react';

export default function Home() {
  const { state, processImage, reset, debugMode, toggleDebugMode } = useScanState();
  const { state: serverState, retry: retryServerCheck } = useServerHealth();
  const t = useTranslations('error');
  const tBug = useTranslations('bugReport');
  const { bugReport: bugReportEnabled } = useFeatureFlags();
  const [showBugReport, setShowBugReport] = useState(false);

  // Show warmup overlay while server is not ready
  if (serverState.status !== 'ready') {
    return <ServerWarmupOverlay state={serverState} onRetry={retryServerCheck} />;
  }

  return (
    <main className="min-h-screen flex flex-col">
      {/* Debug mode toggle */}
      <button
        onClick={toggleDebugMode}
        className="fixed bottom-4 right-4 z-50 p-2 rounded-full transition-colors"
        style={{
          backgroundColor: debugMode ? 'rgba(255, 165, 0, 0.2)' : 'rgba(0, 0, 0, 0.3)',
        }}
        title={debugMode ? 'Debug mode ON' : 'Debug mode OFF'}
      >
        <Wrench
          className="w-4 h-4"
          style={{ color: debugMode ? '#FFA500' : 'rgba(255,255,255,0.3)' }}
        />
      </button>

      {state.status === 'idle' && (
        <CameraCapture onImageSelected={processImage} />
      )}

      {state.status === 'processing' && (
        state.imageUri ? (
          <ScanningOverlay imageUri={state.imageUri} />
        ) : (
          <ProcessingSpinner />
        )
      )}

      {state.status === 'results' && (
        <ResultsView
          response={state.response}
          imageUri={state.imageUri}
          onReset={reset}
        />
      )}

      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
          <p className="text-red-400 text-lg mb-6">{state.message}</p>
          <button
            onClick={reset}
            className="bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100"
          >
            {t('tryAgain')}
          </button>
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
