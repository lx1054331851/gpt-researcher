import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ChatBoxSettings } from "@/types/data";

interface ReportRunSettingsProps {
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
  compact?: boolean;
  className?: string;
}

type ReportRunField = "report_type" | "report_source" | "report_language" | "tone";

type SelectOption = {
  value: string;
  label: string;
};

interface LuxeSelectProps {
  id: string;
  field: ReportRunField;
  label: string;
  value: string;
  options: SelectOption[];
  openField: ReportRunField | null;
  setOpenField: React.Dispatch<React.SetStateAction<ReportRunField | null>>;
  onSelect: (field: ReportRunField, value: string) => void;
  compact: boolean;
}

const TONE_OPTIONS = [
  "Objective",
  "Formal",
  "Analytical",
  "Persuasive",
  "Informative",
  "Explanatory",
  "Descriptive",
  "Critical",
  "Comparative",
  "Speculative",
  "Reflective",
  "Narrative",
  "Humorous",
  "Optimistic",
  "Pessimistic",
  "Simple",
  "Casual",
] as const;

function LuxeSelect({
  id,
  field,
  label,
  value,
  options,
  openField,
  setOpenField,
  onSelect,
  compact,
}: LuxeSelectProps) {
  const isOpen = openField === field;
  const selectedLabel = options.find((option) => option.value === value)?.label ?? options[0]?.label ?? value;

  const triggerClassName = compact
    ? "group relative w-full rounded-lg border border-gray-600/50 bg-gradient-to-b from-gray-800/85 to-gray-900/90 px-3 py-2 pr-8 text-left text-sm text-gray-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-all duration-200 hover:border-cyan-400/35 hover:from-gray-800 hover:to-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/25"
    : "group relative w-full rounded-lg border border-gray-600/50 bg-gradient-to-b from-gray-800/85 to-gray-900/90 px-3.5 py-2.5 pr-9 text-left text-sm text-gray-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-all duration-200 hover:border-cyan-400/35 hover:from-gray-800 hover:to-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/25";

  return (
    <div className={`relative ${isOpen ? "z-[500]" : "z-10"}`}>
      <label htmlFor={id} className={compact ? "mb-1 block text-xs font-semibold tracking-wide text-gray-300" : "mb-1.5 block text-xs font-semibold tracking-wide text-gray-300"}>
        {label}
      </label>

      <button
        id={id}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={triggerClassName}
        onClick={() => setOpenField((prev) => (prev === field ? null : field))}
      >
        <span className="block truncate pr-1">{selectedLabel}</span>
        <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-gray-400">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className={`transition-transform duration-200 ${compact ? "h-3.5 w-3.5" : "h-4 w-4"} ${isOpen ? "rotate-180 text-cyan-300" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      {isOpen && (
        <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-[600] overflow-hidden rounded-xl border border-gray-500/30 bg-gradient-to-b from-gray-800/95 to-gray-900/95 shadow-[0_22px_55px_-18px_rgba(2,8,23,0.9)] backdrop-blur-xl animate-[reportSelectIn_160ms_ease-out]">
          <ul
            role="listbox"
            aria-labelledby={id}
            className={`custom-report-select-scroll overflow-y-auto ${compact ? "max-h-56" : "max-h-64"}`}
          >
            {options.map((option, index) => {
              const selected = option.value === value;
              return (
                <li key={option.value} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    className={`flex w-full items-center justify-between px-3 text-left transition-colors duration-150 ${
                      compact ? "h-10 text-sm" : "h-11 text-[15px]"
                    } ${
                      selected
                        ? "bg-white/[0.10] font-semibold text-white"
                        : "text-gray-200 hover:bg-white/[0.06] hover:text-white"
                    } ${index !== options.length - 1 ? "border-b border-white/[0.06]" : ""}`}
                    onClick={() => {
                      onSelect(field, option.value);
                      setOpenField(null);
                    }}
                  >
                    <span className="truncate">{option.label}</span>
                    {selected && (
                      <span className="text-cyan-300">
                        <svg xmlns="http://www.w3.org/2000/svg" className={compact ? "h-3.5 w-3.5" : "h-4 w-4"} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ReportRunSettings({
  chatBoxSettings,
  setChatBoxSettings,
  compact = false,
  className = "",
}: ReportRunSettingsProps) {
  const t = useTranslations();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [openField, setOpenField] = useState<ReportRunField | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!wrapperRef.current) {
        return;
      }
      if (!wrapperRef.current.contains(event.target as Node)) {
        setOpenField(null);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenField(null);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const handleFieldChange = (field: ReportRunField, value: string) => {
    setChatBoxSettings((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const reportTypeOptions = useMemo<SelectOption[]>(
    () => [
      { value: "research_report", label: t("settings.reportType.summary") },
      { value: "deep", label: t("settings.reportType.deep") },
      { value: "adaptive_deep", label: t("settings.reportType.adaptiveDeep") },
      { value: "multi_agents", label: t("settings.reportType.multiAgents") },
      { value: "detailed_report", label: t("settings.reportType.detailed") },
    ],
    [t]
  );

  const reportSourceOptions = useMemo<SelectOption[]>(
    () => [
      { value: "web", label: t("settings.reportSource.web") },
      { value: "local", label: t("settings.reportSource.local") },
      { value: "hybrid", label: t("settings.reportSource.hybrid") },
    ],
    [t]
  );

  const reportLanguageOptions = useMemo<SelectOption[]>(
    () => [
      { value: "english", label: t("settings.reportLanguage.english") },
      { value: "chinese", label: t("settings.reportLanguage.chinese") },
    ],
    [t]
  );

  const toneOptions = useMemo<SelectOption[]>(
    () =>
      TONE_OPTIONS.map((tone) => ({
        value: tone,
        label: t(`settings.toneOptions.${tone}` as any),
      })),
    [t]
  );

  return (
    <div
      ref={wrapperRef}
      className={`relative z-[400] mt-4 rounded-xl border border-gray-600/35 bg-gradient-to-b from-slate-800/40 to-slate-900/35 p-3 shadow-[0_18px_35px_-18px_rgba(3,7,18,0.85)] backdrop-blur-md sm:p-4 ${className}`}
    >
      <div className={compact ? "grid grid-cols-1 gap-3 sm:grid-cols-2" : "grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4"}>
        <LuxeSelect
          id="home_report_type"
          field="report_type"
          label={t("settings.reportTypeLabel")}
          value={chatBoxSettings.report_type}
          options={reportTypeOptions}
          openField={openField}
          setOpenField={setOpenField}
          onSelect={handleFieldChange}
          compact={compact}
        />

        <LuxeSelect
          id="home_report_source"
          field="report_source"
          label={t("settings.reportSourceLabel")}
          value={chatBoxSettings.report_source}
          options={reportSourceOptions}
          openField={openField}
          setOpenField={setOpenField}
          onSelect={handleFieldChange}
          compact={compact}
        />

        <LuxeSelect
          id="home_report_language"
          field="report_language"
          label={t("settings.reportLanguageLabel")}
          value={chatBoxSettings.report_language || "chinese"}
          options={reportLanguageOptions}
          openField={openField}
          setOpenField={setOpenField}
          onSelect={handleFieldChange}
          compact={compact}
        />

        <LuxeSelect
          id="home_tone"
          field="tone"
          label={t("settings.toneLabel")}
          value={chatBoxSettings.tone}
          options={toneOptions}
          openField={openField}
          setOpenField={setOpenField}
          onSelect={handleFieldChange}
          compact={compact}
        />
      </div>

      <style jsx>{`
        @keyframes reportSelectIn {
          from {
            opacity: 0;
            transform: translateY(6px) scale(0.985);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }

        .custom-report-select-scroll::-webkit-scrollbar {
          width: 6px;
        }

        .custom-report-select-scroll::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.35);
        }

        .custom-report-select-scroll::-webkit-scrollbar-thumb {
          background: rgba(148, 163, 184, 0.35);
          border-radius: 999px;
        }

        .custom-report-select-scroll::-webkit-scrollbar-thumb:hover {
          background: rgba(148, 163, 184, 0.5);
        }
      `}</style>
    </div>
  );
}
