import React, { ChangeEvent } from 'react';
import { useTranslations } from "next-intl";

interface LayoutSelectorProps {
  layoutType: string;
  onLayoutChange: (event: ChangeEvent<HTMLSelectElement>) => void;
}

export default function LayoutSelector({ layoutType, onLayoutChange }: LayoutSelectorProps) {
  const t = useTranslations();

  return (
    <div className="form-group">
      <label htmlFor="layoutType" className="agent_question">{t("settings.layoutLabel")}</label>
      <select 
        name="layoutType" 
        id="layoutType" 
        value={layoutType} 
        onChange={onLayoutChange} 
        className="form-control-static"
        required
      >
        <option value="research">{t("settings.layoutOptions.research")}</option>
        <option value="copilot">{t("settings.layoutOptions.copilot")}</option>
      </select>
    </div>
  );
} 
