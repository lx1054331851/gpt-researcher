import React, { useState, useEffect } from "react";
import FileUpload from "../Settings/FileUpload";
import ToneSelector from "../Settings/ToneSelector";
import MCPSelector from "../Settings/MCPSelector";
import LayoutSelector from "../Settings/LayoutSelector";
import DomainFilter from "./DomainFilter";
import { useAnalytics } from "../../hooks/useAnalytics";
import { ChatBoxSettings, Domain, MCPConfig } from '@/types/data';
import { useTranslations } from "next-intl";
import { useAppLocale } from "@/hooks/useAppLocale";

interface ResearchFormProps {
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
  onFormSubmit?: (
    task: string,
    reportType: string,
    reportSource: string,
    domains: Domain[]
  ) => void;
}

export default function ResearchForm({
  chatBoxSettings,
  setChatBoxSettings,
  onFormSubmit,
}: ResearchFormProps) {
  const t = useTranslations();
  const { locale, setLocale } = useAppLocale();
  const { trackResearchQuery } = useAnalytics();
  const [task, setTask] = useState("");
  const [newDomain, setNewDomain] = useState('');

  // Destructure necessary fields from chatBoxSettings
  let { report_type, report_source, tone, report_language, layoutType } = chatBoxSettings;

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

  const onFormChange = (e: { target: { name: any; value: any } }) => {
    const { name, value } = e.target;
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      [name]: value,
    }));
  };

  const onToneChange = (e: { target: { value: any } }) => {
    const { value } = e.target;
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      tone: value,
    }));
  };

  const onLayoutChange = (e: { target: { value: any } }) => {
    const { value } = e.target;
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      layoutType: value,
    }));
  };

  const onReportLanguageChange = (e: { target: { value: any } }) => {
    const { value } = e.target;
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      report_language: value,
    }));
  };

  const onMCPChange = (enabled: boolean, configs: MCPConfig[]) => {
    setChatBoxSettings((prevSettings: any) => ({
      ...prevSettings,
      mcp_enabled: enabled,
      mcp_configs: configs,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onFormSubmit) {
      const updatedSettings = {
        ...chatBoxSettings,
        domains: domains.map(domain => domain.value)
      };
      setChatBoxSettings(updatedSettings);
      onFormSubmit(task, report_type, report_source, domains);
    }
  };

  return (
    <form
      method="POST"
      className="report_settings_static mt-3"
      onSubmit={handleSubmit}
    >
      <div className="form-group">
        <label htmlFor="report_type" className="agent_question">
          {t("settings.reportTypeLabel")}
        </label>
        <select
          name="report_type"
          value={report_type}
          onChange={onFormChange}
          className="form-control-static"
          required
        >
          <option value="research_report">
            {t("settings.reportType.summary")}
          </option>
          <option value="deep">{t("settings.reportType.deep")}</option>
          <option value="multi_agents">{t("settings.reportType.multiAgents")}</option>
          <option value="detailed_report">
            {t("settings.reportType.detailed")}
          </option>
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="report_source" className="agent_question">
          {t("settings.reportSourceLabel")}
        </label>
        <select
          name="report_source"
          value={report_source}
          onChange={onFormChange}
          className="form-control-static"
          required
        >
          <option value="web">{t("settings.reportSource.web")}</option>
          <option value="local">{t("settings.reportSource.local")}</option>
          <option value="hybrid">{t("settings.reportSource.hybrid")}</option>
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="report_language" className="agent_question">
          {t("settings.reportLanguageLabel")}
        </label>
        <select
          name="report_language"
          id="report_language"
          value={report_language || "english"}
          onChange={onReportLanguageChange}
          className="form-control-static"
          required
        >
          <option value="english">{t("settings.reportLanguage.english")}</option>
          <option value="chinese">{t("settings.reportLanguage.chinese")}</option>
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="ui_language" className="agent_question">
          {t("settings.uiLanguageLabel")}
        </label>
        <select
          name="ui_language"
          id="ui_language"
          value={locale}
          onChange={(e) => setLocale(e.target.value)}
          className="form-control-static"
          required
        >
          <option value="en">{t("settings.uiLanguage.en")}</option>
          <option value="zh-CN">{t("settings.uiLanguage.zh-CN")}</option>
        </select>
      </div>

      {report_source === "local" || report_source === "hybrid" ? (
        <FileUpload />
      ) : null}
      
      <ToneSelector tone={tone} onToneChange={onToneChange} />

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
    </form>
  );
}
