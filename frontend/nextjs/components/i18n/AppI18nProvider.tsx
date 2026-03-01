"use client";

import { NextIntlClientProvider } from "next-intl";
import type { AbstractIntlMessages } from "next-intl";
import React, { createContext, useCallback, useEffect, useMemo, useState } from "react";

import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE_KEY,
  LOCALE_STORAGE_KEY,
  normalizeLocale,
  type AppLocale,
} from "@/i18n/constants";
import { detectClientLocale } from "@/i18n/locale";

import enMessages from "@/messages/en.json";
import zhCNMessages from "@/messages/zh-CN.json";

const ALL_MESSAGES: Record<AppLocale, AbstractIntlMessages> = {
  en: enMessages,
  "zh-CN": zhCNMessages,
};

type AppLocaleContextValue = {
  locale: AppLocale;
  setLocale: (locale: string) => void;
};

export const AppLocaleContext = createContext<AppLocaleContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
});

type AppI18nProviderProps = {
  children: React.ReactNode;
  initialLocale: AppLocale;
  initialMessages: AbstractIntlMessages;
};

function persistLocale(locale: AppLocale): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  document.cookie = `${LOCALE_COOKIE_KEY}=${encodeURIComponent(locale)}; path=/; max-age=31536000; samesite=lax`;
}

export default function AppI18nProvider({
  children,
  initialLocale,
  initialMessages,
}: AppI18nProviderProps) {
  const [locale, setLocaleState] = useState<AppLocale>(initialLocale);
  const [messages, setMessages] = useState<AbstractIntlMessages>(initialMessages);

  const setLocale = useCallback((nextLocale: string) => {
    const normalized = normalizeLocale(nextLocale);
    setLocaleState(normalized);
    setMessages(ALL_MESSAGES[normalized]);
    persistLocale(normalized);
  }, []);

  useEffect(() => {
    const preferredLocale = detectClientLocale();
    if (preferredLocale !== initialLocale) {
      setLocaleState(preferredLocale);
      setMessages(ALL_MESSAGES[preferredLocale]);
    }
  }, [initialLocale]);

  useEffect(() => {
    document.documentElement.lang = locale;
    persistLocale(locale);
  }, [locale]);

  const contextValue = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);

  return (
    <AppLocaleContext.Provider value={contextValue}>
      <NextIntlClientProvider locale={locale} messages={messages}>
        {children}
      </NextIntlClientProvider>
    </AppLocaleContext.Provider>
  );
}
