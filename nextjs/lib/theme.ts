/**
 * Centralized theme constants for the Next.js web app
 *
 * All colors, spacing, and styling constants should be defined here
 * to avoid duplication across components.
 */

// MARK: - Colors

export const colors = {
  /** Primary wine color for buttons and accents */
  wine: '#722F37',

  /** Star rating color (gold) */
  star: '#FFCC00',

  /** Main background color (dark) */
  background: '#1a1a2e',

  /** White text */
  textLight: '#FFFFFF',

  /** Muted/secondary text */
  textMuted: '#999999',

  /** Dark text for light backgrounds */
  textDark: '#000000',

  /** Secondary dark text */
  textSecondary: '#666666',

  /** Processing spinner text */
  textProcessing: '#333333',

  /** Badge background (high-contrast for visibility) */
  badgeBackground: 'rgba(0, 0, 0, 0.85)',

  /** Top-3 border color */
  topThreeBorder: 'rgba(255, 204, 0, 0.6)',

  /** Top-3 glow effect color */
  topThreeGlow: '#FFCC00',

  /** Toast background */
  toastBackground: 'rgba(0, 0, 0, 0.8)',

  /** Separator/divider lines */
  separator: '#E0E0E0',

  /** Modal handle bar */
  handleBar: '#E0E0E0',

  /** Sheet/modal background */
  sheetBackground: '#FFFFFF',

  // Debug tray colors
  /** Debug tray background */
  debugBackground: 'rgba(0, 0, 0, 0.95)',

  /** Debug header background */
  debugHeaderBackground: 'rgba(0, 0, 0, 0.8)',

  /** Debug wrench icon color */
  debugOrange: '#FFA500',

  /** Success status (green) */
  statusSuccess: '#22C55E',

  /** Warning status (yellow) */
  statusWarning: '#EAB308',

  /** Failure status (red) */
  statusFailure: '#EF4444',

  // Button colors
  /** Primary button background (white) */
  buttonPrimaryBackground: '#FFFFFF',

  /** Primary button text (black) */
  buttonPrimaryText: '#000000',

  /** Secondary button background (semi-transparent white) */
  buttonSecondaryBackground: 'rgba(255, 255, 255, 0.2)',

  /** Secondary button text (white) */
  buttonSecondaryText: '#FFFFFF',
  /** Corner bracket color for top-3 wines */
  cornerBracket: 'rgba(255, 204, 0, 0.7)',

  /** Corner bracket color for best pick (#1) */
  cornerBracketBestPick: 'rgba(255, 204, 0, 0.85)',

  // Shelf ranking colors
  /** Gold rank color (#1) */
  rankGold: '#FFD700',

  /** Silver rank color (#2) */
  rankSilver: '#D9D9D9',

  /** Bronze rank color (#3) */
  rankBronze: '#B3B3B3',

  // Safe pick / feature colors
  /** Safe pick green */
  safePick: '#4CAF50',

  /** Wine memory liked (green) */
  memoryLiked: '#34C759',

  /** Wine memory disliked (red) */
  memoryDisliked: '#FF3B30',
} as const;

// MARK: - Corner Bracket Config

export const bracketConfig = {
  /** Arm length as fraction of bbox edge */
  armFraction: 0.18,

  /** Minimum arm length in pixels */
  minArm: 8,

  /** Maximum arm length in pixels */
  maxArm: 40,

  /** Default line width */
  lineWidth: 2,

  /** Best pick line width */
  bestPickLineWidth: 3,
} as const;

// MARK: - Wine Type Colors

/** Colors for wine type badges in detail modal */
export const wineTypeColors: Record<string, string> = {
  Red: '#722F37',
  White: '#F5E6C8',
  Rosé: '#F4C2C2',
  Sparkling: '#FFE4B5',
  Dessert: '#DAA520',
  Fortified: '#8B4513',
} as const;

// MARK: - Spacing

export const spacing = {
  /** Extra small: 4px */
  xs: 4,

  /** Small: 8px */
  sm: 8,

  /** Medium: 16px */
  md: 16,

  /** Large: 24px */
  lg: 24,

  /** Extra large: 32px */
  xl: 32,

  /** Extra extra large: 48px */
  xxl: 48,
} as const;

// MARK: - Border Radius

export const borderRadius = {
  /** Small radius: 2.5px (handle bar) */
  xs: 2.5,

  /** Small radius: 8px */
  sm: 8,

  /** Medium radius: 12px (buttons, badges) */
  md: 12,
} as const;

// MARK: - Font Sizes

export const fontSize = {
  /** Body/small: 15px */
  sm: 15,

  /** Normal: 16px */
  md: 16,

  /** Button/label: 17px */
  lg: 17,

  /** Title: 22px */
  xl: 22,

  /** Large title: 24px */
  xxl: 24,

  /** Rating display: 48px */
  rating: 48,
} as const;

// MARK: - Badge Sizes

export const badgeSizes = {
  /** Base badge dimensions */
  base: {
    width: 44,
    height: 24,
  },

  /** Top-3 badge dimensions (larger) */
  topThree: {
    width: 52,
    height: 28,
  },
} as const;

// MARK: - Animation

export const animation = {
  /** Toast fade duration in ms */
  toastDuration: 300,

  /** Toast auto-dismiss timeout in ms */
  toastTimeout: 3000,
} as const;

// MARK: - Layout

export const layout = {
  /** Toast bottom position */
  toastBottomPosition: 100,

  /** Collision padding for overlay positioning */
  collisionPadding: 4,

  /** Handle bar width */
  handleBarWidth: 36,

  /** Handle bar height */
  handleBarHeight: 5,
} as const;
