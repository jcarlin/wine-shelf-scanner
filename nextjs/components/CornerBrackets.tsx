'use client';

import { BoundingBox, Size } from '@/lib/types';
import { cornerBrackets } from '@/lib/overlay-math';
import { colors, bracketConfig } from '@/lib/theme';

interface CornerBracketsProps {
  bbox: BoundingBox;
  containerSize: Size;
  offset: { x: number; y: number };
  isBestPick: boolean;
}

export function CornerBrackets({ bbox, containerSize, offset, isBestPick }: CornerBracketsProps) {
  const lines = cornerBrackets(bbox, containerSize);
  const stroke = isBestPick ? colors.cornerBracketBestPick : colors.cornerBracket;
  const strokeWidth = isBestPick ? bracketConfig.bestPickLineWidth : bracketConfig.lineWidth;

  return (
    <svg
      style={{
        position: 'absolute',
        left: offset.x,
        top: offset.y,
        width: containerSize.width,
        height: containerSize.height,
        pointerEvents: 'none',
      }}
    >
      {lines.map((line, i) => (
        <line
          key={i}
          x1={line.x1}
          y1={line.y1}
          x2={line.x2}
          y2={line.y2}
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}
