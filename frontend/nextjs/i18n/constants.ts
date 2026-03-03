export const SUPPORTED_LOCALES = ["en", "zh-CN"] as const;

export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: AppLocale = "en";

export const LOCALE_STORAGE_KEY = "gptr_locale";
export const LOCALE_COOKIE_KEY = "gptr_locale";

export const REPORT_LANGUAGES = ["english", "chinese"] as const;

export type ReportLanguage = (typeof REPORT_LANGUAGES)[number];

export const DEFAULT_REPORT_LANGUAGE: ReportLanguage = "chinese";

export function normalizeLocale(locale: string | null | undefined): AppLocale {
  if (!locale) {
    return DEFAULT_LOCALE;
  }

  const normalized = locale.trim().toLowerCase();

  if (normalized.startsWith("zh")) {
    return "zh-CN";
  }

  return "en";
}

export function isSupportedLocale(locale: string): locale is AppLocale {
  return SUPPORTED_LOCALES.includes(locale as AppLocale);
}

export function normalizeReportLanguage(language: string | null | undefined): ReportLanguage {
  if (!language) {
    return DEFAULT_REPORT_LANGUAGE;
  }

  const normalized = language.trim().toLowerCase();

  if (normalized === "chinese") {
    return "chinese";
  }

  return "english";
}
