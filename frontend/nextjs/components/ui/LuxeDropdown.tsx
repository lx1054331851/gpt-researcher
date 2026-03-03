import React, { useEffect, useRef, useState } from "react";

export interface LuxeDropdownOption {
  value: string;
  label: string;
}

interface LuxeDropdownProps {
  id: string;
  label?: string;
  value: string;
  options: LuxeDropdownOption[];
  onChange: (value: string) => void;
  compact?: boolean;
  className?: string;
  labelClassName?: string;
  maxHeightClassName?: string;
}

export default function LuxeDropdown({
  id,
  label,
  value,
  options,
  onChange,
  compact = false,
  className = "",
  labelClassName = "",
  maxHeightClassName = "",
}: LuxeDropdownProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!wrapperRef.current) {
        return;
      }
      if (!wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const selectedLabel = options.find((option) => option.value === value)?.label ?? options[0]?.label ?? value;

  const buttonClassName = compact
    ? "group relative w-full rounded-lg border border-gray-600/50 bg-gradient-to-b from-gray-800/85 to-gray-900/90 px-3 py-2 pr-8 text-left text-sm text-gray-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-all duration-200 hover:border-cyan-400/35 hover:from-gray-800 hover:to-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/25"
    : "group relative w-full rounded-lg border border-gray-600/50 bg-gradient-to-b from-gray-800/85 to-gray-900/90 px-3.5 py-2.5 pr-9 text-left text-sm text-gray-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-all duration-200 hover:border-cyan-400/35 hover:from-gray-800 hover:to-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/25";

  const defaultLabelClassName = compact
    ? "mb-1 block text-xs font-semibold tracking-wide text-gray-300"
    : "mb-1.5 block text-xs font-semibold tracking-wide text-gray-300";

  const menuMaxHeight = maxHeightClassName || (compact ? "max-h-56" : "max-h-64");

  return (
    <div ref={wrapperRef} className={`relative ${open ? "z-[3000]" : "z-10"} ${className}`}>
      {label ? <label htmlFor={id} className={`${defaultLabelClassName} ${labelClassName}`.trim()}>{label}</label> : null}

      <button
        id={id}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        className={buttonClassName}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="block truncate pr-1">{selectedLabel}</span>
        <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-gray-400">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className={`transition-transform duration-200 ${compact ? "h-3.5 w-3.5" : "h-4 w-4"} ${open ? "rotate-180 text-cyan-300" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-[3100] overflow-hidden rounded-xl border border-gray-500/30 bg-gradient-to-b from-gray-800/95 to-gray-900/95 shadow-[0_22px_55px_-18px_rgba(2,8,23,0.9)] backdrop-blur-xl animate-[luxeSelectIn_160ms_ease-out]">
          <ul role="listbox" aria-labelledby={id} className={`custom-luxe-select-scroll overflow-y-auto ${menuMaxHeight}`}>
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
                      onChange(option.value);
                      setOpen(false);
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

      <style jsx>{`
        @keyframes luxeSelectIn {
          from {
            opacity: 0;
            transform: translateY(6px) scale(0.985);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }

        .custom-luxe-select-scroll::-webkit-scrollbar {
          width: 6px;
        }

        .custom-luxe-select-scroll::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.35);
        }

        .custom-luxe-select-scroll::-webkit-scrollbar-thumb {
          background: rgba(148, 163, 184, 0.35);
          border-radius: 999px;
        }

        .custom-luxe-select-scroll::-webkit-scrollbar-thumb:hover {
          background: rgba(148, 163, 184, 0.5);
        }
      `}</style>
    </div>
  );
}
