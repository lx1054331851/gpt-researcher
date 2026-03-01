import { DEFAULT_LOCALE, LOCALE_COOKIE_KEY, LOCALE_STORAGE_KEY, normalizeLocale, type AppLocale } from "@/i18n/constants";

export function detectLocaleFromAcceptLanguage(acceptLanguage: string | null | undefined): AppLocale {
  if (!acceptLanguage) {
    return DEFAULT_LOCALE;
  }

  const candidates = acceptLanguage
    .split(",")
    .map((part) => part.trim().split(";")[0])
    .filter(Boolean);

  for (const candidate of candidates) {
    const locale = normalizeLocale(candidate);
    if (locale) {
      return locale;
    }
  }

  return DEFAULT_LOCALE;
}

export function detectLocaleFromCookie(cookieLocale: string | null | undefined): AppLocale {
  return normalizeLocale(cookieLocale);
}

export function resolveInitialLocale({
  cookieLocale,
  acceptLanguage,
}: {
  cookieLocale?: string | null;
  acceptLanguage?: string | null;
}): AppLocale {
  if (cookieLocale) {
    return detectLocaleFromCookie(cookieLocale);
  }

  return detectLocaleFromAcceptLanguage(acceptLanguage);
}

export function detectClientLocale(): AppLocale {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE;
  }

  const fromStorage = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  if (fromStorage) {
    return normalizeLocale(fromStorage);
  }

  const cookieMatch = document.cookie
    .split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(`${LOCALE_COOKIE_KEY}=`));

  if (cookieMatch) {
    const value = decodeURIComponent(cookieMatch.split("=")[1] || "");
    return normalizeLocale(value);
  }

  return normalizeLocale(navigator.language || navigator.languages?.[0]);
}
