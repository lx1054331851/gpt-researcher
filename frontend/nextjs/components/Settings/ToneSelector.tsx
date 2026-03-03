import React, { ChangeEvent } from 'react';
import { useTranslations } from "next-intl";
import LuxeDropdown from "@/components/ui/LuxeDropdown";

interface ToneSelectorProps {
  tone: string;
  onToneChange: (event: ChangeEvent<HTMLSelectElement>) => void;
}
export default function ToneSelector({ tone, onToneChange }: ToneSelectorProps) {
  const t = useTranslations();

  return (
    <div className="form-group">
      <LuxeDropdown
        id="tone"
        label={t("settings.toneLabel")}
        value={tone}
        onChange={(value) => onToneChange({ target: { value } } as ChangeEvent<HTMLSelectElement>)}
        options={[
          { value: "Objective", label: t("settings.toneOptions.Objective") },
          { value: "Formal", label: t("settings.toneOptions.Formal") },
          { value: "Analytical", label: t("settings.toneOptions.Analytical") },
          { value: "Persuasive", label: t("settings.toneOptions.Persuasive") },
          { value: "Informative", label: t("settings.toneOptions.Informative") },
          { value: "Explanatory", label: t("settings.toneOptions.Explanatory") },
          { value: "Descriptive", label: t("settings.toneOptions.Descriptive") },
          { value: "Critical", label: t("settings.toneOptions.Critical") },
          { value: "Comparative", label: t("settings.toneOptions.Comparative") },
          { value: "Speculative", label: t("settings.toneOptions.Speculative") },
          { value: "Reflective", label: t("settings.toneOptions.Reflective") },
          { value: "Narrative", label: t("settings.toneOptions.Narrative") },
          { value: "Humorous", label: t("settings.toneOptions.Humorous") },
          { value: "Optimistic", label: t("settings.toneOptions.Optimistic") },
          { value: "Pessimistic", label: t("settings.toneOptions.Pessimistic") },
          { value: "Simple", label: t("settings.toneOptions.Simple") },
          { value: "Casual", label: t("settings.toneOptions.Casual") },
        ]}
      />
    </div>
  );
}
