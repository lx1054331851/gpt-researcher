import React, { ChangeEvent } from 'react';
import { useTranslations } from "next-intl";

interface ToneSelectorProps {
  tone: string;
  onToneChange: (event: ChangeEvent<HTMLSelectElement>) => void;
}
export default function ToneSelector({ tone, onToneChange }: ToneSelectorProps) {
  const t = useTranslations();

  return (
    <div className="form-group">
      <label htmlFor="tone" className="agent_question">{t("settings.toneLabel")}</label>
      <select 
        name="tone" 
        id="tone" 
        value={tone} 
        onChange={onToneChange} 
        className="form-control-static"
        required
      >
        <option value="Objective">{t("settings.toneOptions.Objective")}</option>
        <option value="Formal">{t("settings.toneOptions.Formal")}</option>
        <option value="Analytical">{t("settings.toneOptions.Analytical")}</option>
        <option value="Persuasive">{t("settings.toneOptions.Persuasive")}</option>
        <option value="Informative">{t("settings.toneOptions.Informative")}</option>
        <option value="Explanatory">{t("settings.toneOptions.Explanatory")}</option>
        <option value="Descriptive">{t("settings.toneOptions.Descriptive")}</option>
        <option value="Critical">{t("settings.toneOptions.Critical")}</option>
        <option value="Comparative">{t("settings.toneOptions.Comparative")}</option>
        <option value="Speculative">{t("settings.toneOptions.Speculative")}</option>
        <option value="Reflective">{t("settings.toneOptions.Reflective")}</option>
        <option value="Narrative">{t("settings.toneOptions.Narrative")}</option>
        <option value="Humorous">{t("settings.toneOptions.Humorous")}</option>
        <option value="Optimistic">{t("settings.toneOptions.Optimistic")}</option>
        <option value="Pessimistic">{t("settings.toneOptions.Pessimistic")}</option>
        <option value="Simple">{t("settings.toneOptions.Simple")}</option>
        <option value="Casual">{t("settings.toneOptions.Casual")}</option>
      </select>
    </div>
  );
}
