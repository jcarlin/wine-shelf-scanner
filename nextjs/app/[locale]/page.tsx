'use client';

import { useTranslations } from 'next-intl';
import { CameraCapture, ProcessingSpinner, ScanningOverlay, ResultsView } from '@/components';
import { useScanState } from '@/hooks/useScanState';

export default function Home() {
  const { state, processImage, reset } = useScanState();
  const t = useTranslations('error');

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
            {t('tryAgain')}
          </button>
        </div>
      )}
    </main>
  );
}
