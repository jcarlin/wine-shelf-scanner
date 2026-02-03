'use client';

import { Star } from 'lucide-react';
import { WineResult } from '@/lib/types';
import { colors, badgeSizes } from '@/lib/theme';
import { opacity as getOpacity, isTappable } from '@/lib/overlay-math';

interface RatingBadgeProps {
  wine: WineResult;
  isTopThree: boolean;
  position: { x: number; y: number };
  onClick?: () => void;
}

export function RatingBadge({ wine, isTopThree, position, onClick }: RatingBadgeProps) {
  const badgeOpacity = getOpacity(wine.confidence);
  const canTap = isTappable(wine.confidence);
  const size = isTopThree ? badgeSizes.topThree : badgeSizes.base;

  console.log('[RatingBadge] Rendering', wine.wine_name, {
    position,
    opacity: badgeOpacity,
    confidence: wine.confidence,
    size
  });

  // Don't render if opacity is 0
  if (badgeOpacity === 0) {
    console.log('[RatingBadge] Skipping', wine.wine_name, '- opacity is 0');
    return null;
  }

  const handleClick = () => {
    if (canTap && onClick) {
      onClick();
    }
  };

  return (
    <div
      className={`
        absolute flex items-center justify-center gap-1 rounded-lg
        transform -translate-x-1/2 -translate-y-1/2
        transition-all duration-200
        ${canTap ? 'cursor-pointer hover:scale-110' : 'cursor-default'}
        ${isTopThree ? 'shadow-lg' : ''}
      `}
      style={{
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
        opacity: badgeOpacity,
        backgroundColor: colors.badgeBackground,
        borderWidth: isTopThree ? 2 : 0,
        borderColor: isTopThree ? colors.topThreeBorder : 'transparent',
        boxShadow: isTopThree ? `0 0 12px ${colors.topThreeGlow}40` : undefined,
        zIndex: 10,
      }}
      onClick={handleClick}
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
    </div>
  );
}
