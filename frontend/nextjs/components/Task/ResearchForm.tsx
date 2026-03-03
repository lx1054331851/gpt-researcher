import React, { useState, useEffect } from "react";
import FileUpload from "../Settings/FileUpload";
import MCPSelector from "../Settings/MCPSelector";
import LayoutSelector from "../Settings/LayoutSelector";
import LuxeDropdown from "@/components/ui/LuxeDropdown";
import DomainFilter from "./DomainFilter";
import { ChatBoxSettings, Domain, MCPConfig } from '@/types/data';
import { useTranslations } from "next-intl";
import { useAppLocale } from "@/hooks/useAppLocale";

interface ResearchFormProps {
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
}

export default function ResearchForm({
  chatBoxSettings,
  setChatBoxSettings,
}: ResearchFormProps) {
  const t = useTranslations();
  const { locale, setLocale } = useAppLocale();
  const [newDomain, setNewDomain] = useState('');

  // Destructure necessary fields from chatBoxSettings
  let { report_source, layoutType } = chatBoxSettings;

  const [domains, setDomains] = useState<Domain[]>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('domainFilters');
      return saved ? JSON.parse(saved) : [];
    }
    return [];
  });
  
  useEffect(() => {
    localStorage.setItem('domainFilters', JSON.stringify(domains));
    setChatBoxSettings(prev => ({
      ...prev,
      domains: domains.map(domain => domain.value)
    }));
  }, [domains, setChatBoxSettings]);

  const handleAddDomain = (e: React.FormEvent) => {
    e.preventDefault();
    if (newDomain.trim()) {
      setDomains([...domains, { value: newDomain.trim() }]);
      setNewDomain('');
    }
  };

  const handleRemoveDomain = (domainToRemove: string) => {
    setDomains(domains.filter(domain => domain.value !== domainToRemove));
  };

  const onLayoutChange = (value: string) => {
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      layoutType: value,
    }));
  };

  const onMCPChange = (enabled: boolean, configs: MCPConfig[]) => {
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      mcp_enabled: enabled,
      mcp_configs: configs,
    }));
  };

  return (
    <div className="report_settings_static mt-3">
      <div className="form-group">
        <LuxeDropdown
          id="ui_language"
          label={t("settings.uiLanguageLabel")}
          value={locale}
          onChange={setLocale}
          options={[
            { value: "en", label: t("settings.uiLanguage.en") },
            { value: "zh-CN", label: t("settings.uiLanguage.zh-CN") },
          ]}
        />
      </div>

      {report_source === "local" || report_source === "hybrid" ? (
        <FileUpload />
      ) : null}

      <MCPSelector 
        mcpEnabled={chatBoxSettings.mcp_enabled || false}
        mcpConfigs={chatBoxSettings.mcp_configs || []}
        onMCPChange={onMCPChange}
      />
      
      <LayoutSelector layoutType={layoutType || 'copilot'} onLayoutChange={onLayoutChange} />

      {/** TODO: move the below to its own component */}
      {(chatBoxSettings.report_source === "web" || chatBoxSettings.report_source === "hybrid") && (
        <DomainFilter
          domains={domains}
          newDomain={newDomain}
          setNewDomain={setNewDomain}
          onAddDomain={handleAddDomain}
          onRemoveDomain={handleRemoveDomain}
        />
      )}
    </div>
  );
}
