'use client';

import { useState } from 'react';
import { CameraCapture, ProcessingSpinner, ScanningOverlay, ResultsView, BugReportModal } from '@/components';
import { useScanState } from '@/hooks/useScanState';
import { useFeatureFlags } from '@/lib/feature-flags';
import { Flag } from 'lucide-react';

export default function Home() {
  const { state, processImage, reset } = useScanState();
  const { bugReport: bugReportEnabled } = useFeatureFlags();
  const [showBugReport, setShowBugReport] = useState(false);

  return (
    <main className="min-h-screen flex flex-col">
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
            Try Again
          </button>
          {bugReportEnabled && (
            <button
              onClick={() => setShowBugReport(true)}
              className="mt-4 flex items-center gap-1.5 text-gray-500 hover:text-gray-300 text-sm transition-colors"
            >
              <Flag className="w-3.5 h-3.5" />
              Report an Issue
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
