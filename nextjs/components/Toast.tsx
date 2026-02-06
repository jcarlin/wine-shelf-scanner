'use client';

import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { colors, animation } from '@/lib/theme';

interface ToastProps {
  message: string;
  duration?: number;
  onDismiss?: () => void;
}

export function Toast({ message, duration = animation.toastTimeout, onDismiss }: ToastProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(() => {
        onDismiss?.();
      }, animation.toastDuration);
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onDismiss]);

  return (
    <div
      className={`
        fixed bottom-24 left-1/2 transform -translate-x-1/2
        flex items-center gap-2 px-4 py-3 rounded-lg
        border border-yellow-500/40 shadow-lg shadow-black/30
        transition-opacity duration-300
        ${isVisible ? 'opacity-100' : 'opacity-0'}
      `}
      style={{ backgroundColor: colors.toastBackground }}
    >
      <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0" />
      <span className="text-white text-sm font-medium">{message}</span>
    </div>
  );
}
