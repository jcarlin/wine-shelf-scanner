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
  /** Staggered entrance delay in ms — each badge pops in on its bottle */
  entranceDelay?: number;
}

export function RatingBadge({ wine, isTopThree, position, onClick, shelfRank, isSafePick, userSentiment, entranceDelay = 0 }: RatingBadgeProps) {
  const { visualEmphasis } = useFeatureFlags();
  const baseOpacity = getOpacity(wine.confidence);
  const canTap = isTappable(wine.confidence);
  const size = isTopThree ? badgeSizes.topThree : badgeSizes.base;
  const isBestPick = visualEmphasis && shelfRank === 1;

  // Don't render if opacity is 0
  if (baseOpacity === 0) return null;

  // Apply visual emphasis: boost #1 most, top-3 next, dim non-top-3
  let badgeOpacity = baseOpacity;
  if (visualEmphasis && baseOpacity > 0) {
    if (isBestPick) {
      badgeOpacity = Math.min(baseOpacity + 0.35, 1.0);
    } else if (isTopThree) {
      badgeOpacity = Math.min(baseOpacity + 0.25, 1.0);
    } else {
      badgeOpacity = baseOpacity * 0.85;
    }
  }

  const handleClick = () => {
    if (canTap && onClick) {
      onClick();
    }
  };

  const rankColor = shelfRank === 1 ? colors.rankGold : shelfRank === 2 ? colors.rankSilver : colors.rankBronze;

  return (
    <div
      data-testid="rating-badge"
      data-wine-name={wine.wine_name}
      className="absolute flex flex-col items-center animate-badge-pop-in"
      style={{
        left: position.x,
        top: position.y,
        '--badge-opacity': 1, // badgeOpacity,
        animationDelay: `${entranceDelay}ms`,
        zIndex: isBestPick ? 20 : 10,
      } as React.CSSProperties}
      onClick={handleClick}
    >
      {/* Best Pick label above #1 badge */}
      {isBestPick && (
        <span
          className="font-black tracking-wide"
          style={{
            fontSize: 8,
            color: colors.rankGold,
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
            borderWidth: isTopThree ? (isBestPick ? 2.5 : 2) : 1,
            borderColor: isTopThree
              ? (isBestPick ? 'rgba(255, 204, 0, 0.9)' : colors.topThreeBorder)
              : 'rgba(255, 255, 255, 0.3)',
            boxShadow: isBestPick
              ? `0 0 16px rgba(255, 204, 0, 0.6), 0 0 4px rgba(255, 204, 0, 0.3)`
              : isTopThree
                ? `0 0 12px ${colors.topThreeGlow}40`
                : '0 0 6px rgba(0, 0, 0, 0.5)',
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
            data-testid="rating-value"
            className="text-white font-bold"
            style={{ fontSize: isTopThree ? 14 : 12 }}
          >
            {wine.rating?.toFixed(1) ?? '?'}
          </span>
          {isSafePick && (
            <ShieldCheck
              style={{ color: colors.safePick, width: 10, height: 10 }}
            />
          )}
        </div>
        {userSentiment && (
          <div className="absolute -top-1.5 -right-1.5" style={{ filter: 'drop-shadow(0 0 1px rgba(0,0,0,0.8))' }}>
            {userSentiment === 'disliked' ? (
              <XCircle style={{ color: colors.memoryDisliked, width: 12, height: 12 }} />
            ) : (
              <Heart className="fill-current" style={{ color: colors.memoryLiked, width: 12, height: 12 }} />
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
