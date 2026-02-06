'use client';

import { useTranslations } from 'next-intl';
import { Wine, RefreshCw } from 'lucide-react';
import { colors } from '@/lib/theme';
import { ServerHealthState } from '@/hooks/useServerHealth';
import { useTipRotation } from '@/hooks/useTipRotation';

const WARMUP_TIP_COUNT = 30;

interface ServerWarmupOverlayProps {
  state: ServerHealthState;
  onRetry: () => void;
}

export function ServerWarmupOverlay({ state, onRetry }: ServerWarmupOverlayProps) {
  const t = useTranslations('warmup');
  const tipIndex = useTipRotation(WARMUP_TIP_COUNT, 4000);

  const tipKey = `tip${tipIndex + 1}` as const;

  if (state.status === 'checking') {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#1a1a2e]">
        <div className="relative mb-8">
          <div
            className="w-24 h-24 rounded-full flex items-center justify-center animate-pulse"
            style={{ backgroundColor: colors.wine }}
          >
            <Wine className="w-12 h-12 text-white" />
          </div>
          <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-star animate-spin" />
        </div>
        <p className="text-gray-400 text-center">{t('checking')}</p>
      </div>
    );
  }

  if (state.status === 'warming_up') {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#1a1a2e] px-6">
        <div className="relative mb-8">
          <div
            className="w-24 h-24 rounded-full flex items-center justify-center"
            style={{ backgroundColor: colors.wine }}
          >
            <Wine className="w-12 h-12 text-white" />
          </div>
          <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-star animate-spin" />
        </div>

        <h2 className="text-xl font-semibold text-white mb-2">{t('title')}</h2>
        <p className="text-gray-400 text-center max-w-sm mb-4">{t('message')}</p>

        <div className="flex gap-2 mb-6">
          <div className="w-2 h-2 rounded-full bg-star animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 rounded-full bg-star animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 rounded-full bg-star animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>

        <p
          key={tipIndex}
          className="text-gray-500 text-sm text-center max-w-xs italic animate-fade-in"
        >
          {t(tipKey)}
        </p>
      </div>
    );
  }

  if (state.status === 'unavailable') {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#1a1a2e] px-6">
        <div
          className="w-24 h-24 rounded-full flex items-center justify-center mb-8 opacity-50"
          style={{ backgroundColor: colors.wine }}
        >
          <Wine className="w-12 h-12 text-white" />
        </div>

        <h2 className="text-xl font-semibold text-white mb-2">{t('unavailableTitle')}</h2>
        <p className="text-gray-400 text-center max-w-sm mb-6">{state.message}</p>

        <button
          onClick={onRetry}
          className="flex items-center gap-2 bg-white text-black font-semibold py-3 px-8 rounded-xl hover:bg-gray-100"
        >
          <RefreshCw className="w-4 h-4" />
          {t('retry')}
        </button>
      </div>
    );
  }

  return null;
}
