"use client";

import { useContext } from "react";

import { AppLocaleContext } from "@/components/i18n/AppI18nProvider";

export function useAppLocale() {
  return useContext(AppLocaleContext);
}
