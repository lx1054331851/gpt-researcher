import React from 'react';
import { useTranslations } from "next-intl";
import LuxeDropdown from "@/components/ui/LuxeDropdown";

interface LayoutSelectorProps {
  layoutType: string;
  onLayoutChange: (value: string) => void;
}

export default function LayoutSelector({ layoutType, onLayoutChange }: LayoutSelectorProps) {
  const t = useTranslations();

  return (
    <div className="form-group">
      <LuxeDropdown
        id="layoutType"
        label={t("settings.layoutLabel")}
        value={layoutType}
        onChange={onLayoutChange}
        options={[
          { value: "research", label: t("settings.layoutOptions.research") },
          { value: "copilot", label: t("settings.layoutOptions.copilot") },
        ]}
      />
    </div>
  );
} 
