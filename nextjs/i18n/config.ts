export const locales = ['en', 'es', 'fr', 'it', 'de', 'pt', 'zh', 'ru', 'ja', 'ko'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'en';
