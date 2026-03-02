"use client";

import { useTranslations } from "next-intl";
import { useAppLocale } from "@/hooks/useAppLocale";

interface LanguageToggleProps {
  className?: string;
}

export default function LanguageToggle({ className = "" }: LanguageToggleProps) {
  const t = useTranslations();
  const { locale, setLocale } = useAppLocale();

  const nextLocale = locale === "en" ? "zh-CN" : "en";
  const buttonLabel = locale === "en" ? "中" : "EN";

  return (
    <button
      type="button"
      onClick={() => setLocale(nextLocale)}
      aria-label={t("settings.uiLanguageLabel")}
      title={t("settings.uiLanguageLabel")}
      className={`flex items-center justify-center h-9 min-w-[44px] px-3 rounded-full border border-gray-600/60 bg-gray-900/70 text-gray-100 hover:bg-gray-800 transition-colors text-xs font-semibold ${className}`}
    >
      {buttonLabel}
    </button>
  );
}

