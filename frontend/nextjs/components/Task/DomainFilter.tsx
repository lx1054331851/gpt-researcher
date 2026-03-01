import React from "react";
import { Domain } from "@/types/data";
import { useTranslations } from "next-intl";

interface DomainFilterProps {
  domains: Domain[];
  newDomain: string;
  setNewDomain: React.Dispatch<React.SetStateAction<string>>;
  onAddDomain: (e: React.FormEvent) => void;
  onRemoveDomain: (domainToRemove: string) => void;
}

export default function DomainFilter({
  domains,
  newDomain,
  setNewDomain,
  onAddDomain,
  onRemoveDomain,
}: DomainFilterProps) {
  const t = useTranslations();

  return (
    <div className="mt-4 domain_filters">
      <div className="flex gap-2 mb-4">
        <label htmlFor="domain_filters" className="agent_question">
          {t("settings.domainFilter.label")}
        </label>
        <input
          type="text"
          value={newDomain}
          onChange={(e) => setNewDomain(e.target.value)}
          placeholder={t("settings.domainFilter.placeholder")}
          className="input-static"
          onKeyPress={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onAddDomain(e);
            }
          }}
        />
        <button
          type="button"
          onClick={onAddDomain}
          className="button-static"
        >
          {t("settings.domainFilter.add")}
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {domains.map((domain, index) => (
          <div key={index} className="domain-tag-static">
            <span className="domain-text-static">{domain.value}</span>
            <button
              type="button"
              onClick={() => onRemoveDomain(domain.value)}
              className="domain-button-static"
            >
              X
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
