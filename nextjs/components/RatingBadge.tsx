'use client';

import { Star, ShieldCheck, XCircle, Heart } from 'lucide-react';
import { WineResult } from '@/lib/types';
import { colors, badgeSizes } from '@/lib/theme';
import { opacity as getOpacity, isTappable } from '@/lib/overlay-math';
import { useFeatureFlags } from '@/lib/feature-flags';

export type WineSentiment = 'liked' | 'disliked';

interface RatingBadgeProps {
  wine: WineResult;
  isTopThree: boolean;
  position: { x: number; y: number };
  onClick?: () => void;
  shelfRank?: number;
  isSafePick?: boolean;
  userSentiment?: WineSentiment;
}

export function RatingBadge({ wine, isTopThree, position, onClick, shelfRank, isSafePick, userSentiment }: RatingBadgeProps) {
  const { visualEmphasis } = useFeatureFlags();
  const baseOpacity = getOpacity(wine.confidence);
  const canTap = isTappable(wine.confidence);
  const size = isTopThree ? badgeSizes.topThree : badgeSizes.base;
  const isBestPick = visualEmphasis && shelfRank === 1;

  // Don't render if opacity is 0
  if (baseOpacity === 0) return null;

  // Apply visual emphasis: boost top-3 opacity, dim non-top-3
  let badgeOpacity = baseOpacity;
  if (visualEmphasis && baseOpacity > 0) {
    if (isTopThree) {
      badgeOpacity = Math.min(baseOpacity + 0.15, 1.0);
    } else {
      badgeOpacity = baseOpacity * 0.65;
    }
  }

  const handleClick = () => {
    if (canTap && onClick) {
      onClick();
    }
  };

  const rankColor = shelfRank === 1 ? '#FFD700' : shelfRank === 2 ? '#D9D9D9' : '#B3B3B3';

  return (
    <div
      className="absolute flex flex-col items-center transform -translate-x-1/2 -translate-y-1/2"
      style={{
        left: position.x,
        top: position.y,
        opacity: badgeOpacity,
        zIndex: isBestPick ? 20 : 10,
      }}
      onClick={handleClick}
    >
      {/* Best Pick label above #1 badge */}
      {isBestPick && (
        <span
          className="font-black tracking-wide"
          style={{
            fontSize: 8,
            color: '#FFD700',
            textShadow: '0 1px 2px rgba(0,0,0,0.8)',
            marginBottom: 2,
          }}
        >
          BEST PICK
        </span>
      )}
      <div className="relative">
        <div
          className={`
            flex items-center justify-center gap-1 rounded-lg
            transition-all duration-200
            ${canTap ? 'cursor-pointer hover:scale-110' : 'cursor-default'}
            ${isTopThree ? 'shadow-lg' : ''}
          `}
          style={{
            width: size.width,
            height: size.height,
            backgroundColor: colors.badgeBackground,
            borderWidth: isTopThree ? (isBestPick ? 2.5 : 2) : 0,
            borderColor: isTopThree
              ? (isBestPick ? 'rgba(255, 204, 0, 0.9)' : colors.topThreeBorder)
              : 'transparent',
            boxShadow: isBestPick
              ? `0 0 16px rgba(255, 204, 0, 0.6), 0 0 4px rgba(255, 204, 0, 0.3)`
              : isTopThree
                ? `0 0 12px ${colors.topThreeGlow}40`
                : undefined,
          }}
        >
          <Star
            className="fill-current"
            style={{
              color: colors.star,
              width: isTopThree ? 14 : 12,
              height: isTopThree ? 14 : 12,
            }}
          />
          <span
            className="text-white font-bold"
            style={{ fontSize: isTopThree ? 14 : 12 }}
          >
            {wine.rating?.toFixed(1) ?? '?'}
          </span>
          {isSafePick && (
            <ShieldCheck
              style={{ color: '#4CAF50', width: 10, height: 10 }}
            />
          )}
        </div>
        {userSentiment && (
          <div className="absolute -top-1.5 -right-1.5" style={{ filter: 'drop-shadow(0 0 1px rgba(0,0,0,0.8))' }}>
            {userSentiment === 'disliked' ? (
              <XCircle style={{ color: '#FF3B30', width: 12, height: 12 }} />
            ) : (
              <Heart className="fill-current" style={{ color: '#34C759', width: 12, height: 12 }} />
            )}
          </div>
        )}
      </div>
      {shelfRank !== undefined && (
        <span
          className="font-bold"
          style={{
            fontSize: shelfRank === 1 ? 10 : 9,
            color: rankColor,
            textShadow: '0 1px 2px rgba(0,0,0,0.8)',
            marginTop: 2,
          }}
        >
          #{shelfRank}
        </span>
      )}
    </div>
  );
}
