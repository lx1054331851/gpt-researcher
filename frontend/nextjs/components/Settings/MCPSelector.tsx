import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from "next-intl";

interface MCPConfig {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
}

interface MCPSelectorProps {
  mcpEnabled: boolean;
  mcpConfigs: MCPConfig[];
  onMCPChange: (enabled: boolean, configs: MCPConfig[]) => void;
}

const MCPSelector: React.FC<MCPSelectorProps> = ({
  mcpEnabled,
  mcpConfigs,
  onMCPChange,
}) => {
  const t = useTranslations();
  const [enabled, setEnabled] = useState(mcpEnabled);
  const [configText, setConfigText] = useState(() => {
    // Initialize with the passed configs, handling empty array case
    if (Array.isArray(mcpConfigs) && mcpConfigs.length > 0) {
      return JSON.stringify(mcpConfigs, null, 2);
    }
    return '[]';
  });
  const [validationStatus, setValidationStatus] = useState<{
    isValid: boolean;
    message: string;
    serverCount?: number;
  }>({ isValid: true, message: t("settings.mcp.validJson") });
  const [showInfoModal, setShowInfoModal] = useState(false);

  // Sync with props when they change (for localStorage loading)
  useEffect(() => {
    setEnabled(mcpEnabled);
  }, [mcpEnabled]);

  useEffect(() => {
    if (Array.isArray(mcpConfigs)) {
      const newConfigText = mcpConfigs.length > 0 ? JSON.stringify(mcpConfigs, null, 2) : '[]';
      setConfigText(newConfigText);
    }
  }, [mcpConfigs]);

  const validateConfig = useCallback((text: string) => {
    if (!text.trim() || text.trim() === '[]') {
      setValidationStatus({ isValid: true, message: t("settings.mcp.emptyConfiguration") });
      return true;
    }

    try {
      const parsed = JSON.parse(text);

      if (!Array.isArray(parsed)) {
        throw new Error(t("settings.mcp.errors.mustBeArray"));
      }

      const errors: string[] = [];
      parsed.forEach((server: any, index: number) => {
        if (!server.name) {
          errors.push(t("settings.mcp.errors.missingName", { index: index + 1 }));
        }
        if (!server.command && !server.connection_url) {
          errors.push(t("settings.mcp.errors.missingCommandOrConnectionUrl", { index: index + 1 }));
        }
      });

      if (errors.length > 0) {
        throw new Error(errors.join('; '));
      }

      setValidationStatus({
        isValid: true,
        message: t("settings.mcp.validJsonWithCount", { count: parsed.length }),
        serverCount: parsed.length
      });
      return true;
    } catch (error: any) {
      setValidationStatus({
        isValid: false,
        message: `${t("settings.mcp.invalidJson")}: ${error.message}`
      });
      return false;
    }
  }, [t]);

  useEffect(() => {
    validateConfig(configText);
  }, [configText, validateConfig]);

  const handleEnabledChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEnabled = e.target.checked;
    console.log('🔍 DEBUG: MCP enabled changed to:', newEnabled);
    setEnabled(newEnabled);

    if (newEnabled && validationStatus.isValid) {
      try {
        const configs = JSON.parse(configText || '[]');
        console.log('🔍 DEBUG: Calling onMCPChange with configs:', configs);
        onMCPChange(newEnabled, configs);
      } catch {
        console.log('🔍 DEBUG: JSON parse failed, calling with empty array');
        onMCPChange(newEnabled, []);
      }
    } else {
      console.log('🔍 DEBUG: Disabled or invalid, calling with empty array');
      onMCPChange(newEnabled, []);
    }
  };

  const handleConfigChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newText = e.target.value;
    console.log('🔍 DEBUG: Config text changed to:', newText);
    setConfigText(newText);

    if (enabled && validateConfig(newText)) {
      try {
        const configs = JSON.parse(newText || '[]');
        console.log('🔍 DEBUG: Parsed configs from textarea:', configs);
        console.log('🔍 DEBUG: Calling onMCPChange from textarea with:', { enabled, configs });
        onMCPChange(enabled, configs);
      } catch {
        console.log('🔍 DEBUG: JSON parse failed in textarea change');
        // Invalid JSON, don't update
      }
    }
  };

  const formatJSON = () => {
    try {
      const parsed = JSON.parse(configText || '[]');
      const formatted = JSON.stringify(parsed, null, 2);
      setConfigText(formatted);
    } catch {
      // Invalid JSON, don't format
    }
  };

  // Helper function to check if a preset is currently selected
  const isPresetSelected = (presetName: string): boolean => {
    try {
      const currentText = configText.trim();
      if (!currentText || currentText === '[]') return false;
      
      const parsed = JSON.parse(currentText);
      if (!Array.isArray(parsed)) return false;
      
      return parsed.some(server => server.name === presetName);
    } catch {
      return false;
    }
  };

  const togglePreset = (preset: string) => {
    console.log('🔍 DEBUG: togglePreset called with:', preset);
    console.log('🔍 DEBUG: Current configText:', configText);
    console.log('🔍 DEBUG: MCP enabled:', enabled);
    
    const presets: Record<string, MCPConfig> = {
      github: {
        name: 'github',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-github'],
        env: {
          GITHUB_PERSONAL_ACCESS_TOKEN: 'your_github_token_here'
        }
      },
      tavily: {
        name: 'tavily',
        command: 'npx',
        args: ['-y', 'tavily-mcp@0.1.2'],
        env: {
          TAVILY_API_KEY: 'your_tavily_api_key_here'
        }
      },
      filesystem: {
        name: 'filesystem',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-filesystem', '/path/to/allowed/directory'],
        env: {}
      }
    };

    const config = presets[preset];
    if (!config) {
      console.log('🔍 DEBUG: Preset config not found for:', preset);
      return;
    }

    try {
      let currentConfig: MCPConfig[] = [];
      const currentText = configText.trim();

      if (currentText && currentText !== '[]') {
        currentConfig = JSON.parse(currentText);
      }
      console.log('🔍 DEBUG: Current parsed config:', currentConfig);

      const existingIndex = currentConfig.findIndex(server => server.name === config.name);
      console.log('🔍 DEBUG: Existing index for', config.name, ':', existingIndex);

      if (existingIndex !== -1) {
        // Remove the preset if it exists (deselect)
        console.log('🔍 DEBUG: Removing preset');
        currentConfig.splice(existingIndex, 1);
      } else {
        // Add the preset if it doesn't exist (select)
        console.log('🔍 DEBUG: Adding preset');
        currentConfig.push(config);
      }

      const newText = JSON.stringify(currentConfig, null, 2);
      console.log('🔍 DEBUG: New config text:', newText);
      console.log('🔍 DEBUG: Final config array:', currentConfig);
      
      setConfigText(newText);
      
      // IMPORTANT: Also call onMCPChange immediately with the new config
      if (enabled) {
        console.log('🔍 DEBUG: Calling onMCPChange from togglePreset with:', { enabled, currentConfig });
        onMCPChange(enabled, currentConfig);
      }
      
    } catch (error) {
      console.error('🔍 DEBUG: Error toggling preset:', error);
    }
  };

  const showExample = () => {
    const exampleConfig = [
      {
        name: 'github',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-github'],
        env: {
          GITHUB_PERSONAL_ACCESS_TOKEN: 'your_github_token_here'
        }
      },
      {
        name: 'filesystem',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-filesystem', '/path/to/allowed/directory'],
        env: {}
      }
    ];

    setConfigText(JSON.stringify(exampleConfig, null, 2));
  };

  return (
    <div className="form-group">
      <div className="settings mcp-section">
        <div className="settings mcp-header">
          <label className="agent_question">
            <input
              type="checkbox"
              className="settings mcp-toggle"
              checked={enabled}
              onChange={handleEnabledChange}
            />
            {t("settings.mcp.enable")}
          </label>
          <button
            type="button"
            className="settings mcp-info-btn"
            onClick={() => setShowInfoModal(true)}
            title={t("settings.mcp.learnMore")}
          >
            ℹ️
          </button>
        </div>
        <small className="text-muted" style={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: '0.85rem', marginBottom: '15px', display: 'block' }}>
          {t("settings.mcp.subtitle")}
        </small>

        {enabled && (
          <div className="settings mcp-config-section">
            <div className="settings mcp-presets">
              <label className="agent_question" style={{ marginBottom: '10px' }}>{t("settings.mcp.quickPresets")}</label>
              <div className="settings preset-buttons">
                <button
                  type="button"
                  className={`settings preset-btn ${isPresetSelected('github') ? 'selected' : ''}`}
                  onClick={() => togglePreset('github')}
                >
                  <i className="fab fa-github"></i> {t("settings.mcp.presetGithub")}
                </button>
                <button
                  type="button"
                  className={`settings preset-btn ${isPresetSelected('tavily') ? 'selected' : ''}`}
                  onClick={() => togglePreset('tavily')}
                >
                  <i className="fas fa-search"></i> {t("settings.mcp.presetTavily")}
                </button>
                <button
                  type="button"
                  className={`settings preset-btn ${isPresetSelected('filesystem') ? 'selected' : ''}`}
                  onClick={() => togglePreset('filesystem')}
                >
                  <i className="fas fa-folder"></i> {t("settings.mcp.presetFilesystem")}
                </button>
              </div>
              <small className="text-muted" style={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: '0.85rem', marginTop: '8px', display: 'block' }}>
                {t("settings.mcp.presetsHelp")}
              </small>
            </div>

            <div className="settings mcp-config-group">
              <label className="agent_question" style={{ marginBottom: '10px' }}>{t("settings.mcp.configurationTitle")}</label>
              <textarea
                className={`settings mcp-config-textarea ${validationStatus.isValid ? 'valid' : 'invalid'}`}
                rows={12}
                placeholder={t("settings.mcp.configurationPlaceholder")}
                value={configText}
                onChange={handleConfigChange}
                style={{ minHeight: '300px' }}
              />
              <div className="settings mcp-config-status">
                <span className={`settings mcp-status-text ${validationStatus.isValid ? 'valid' : 'invalid'}`}>
                  {validationStatus.message}
                </span>
                <button
                  type="button"
                  className="settings mcp-format-btn"
                  onClick={formatJSON}
                >
                  <i className="fas fa-code"></i> {t("settings.mcp.formatJson")}
                </button>
              </div>
              <small className="text-muted" style={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: '0.85rem', marginTop: '8px', display: 'block', lineHeight: '1.4' }}>
                {t("settings.mcp.configurationHelp")}{' '}
                <code style={{ backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', color: '#0d9488' }}>name</code>,{' '}
                <code style={{ backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', color: '#0d9488' }}>command</code>,{' '}
                <code style={{ backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', color: '#0d9488' }}>args</code>,{' '}
                {t("settings.mcp.configurationHelpSuffix")}{' '}
                <code style={{ backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '2px 4px', borderRadius: '3px', color: '#0d9488' }}>env</code>{' '}
                {t("settings.mcp.configurationHelpVariables")}{' '}
                <a
                  href="#"
                  className="settings mcp-example-link"
                  onClick={(e) => { e.preventDefault(); showExample(); }}
                  style={{ color: '#0d9488', textDecoration: 'none', fontWeight: '500' }}
                >
                  {t("settings.mcp.seeExample")}
                </a>
              </small>
            </div>
          </div>
        )}

        {/* MCP Info Modal */}
        {showInfoModal && (
          <div className="settings mcp-info-modal visible">
            <div className="settings mcp-info-content">
              <button
                className="settings mcp-info-close"
                onClick={() => setShowInfoModal(false)}
              >
                <i className="fas fa-times"></i>
              </button>
              <h3>{t("settings.mcp.modal.title")}</h3>
              <p>{t("settings.mcp.modal.intro")}</p>

              <h4 className="highlight">{t("settings.mcp.modal.benefitsTitle")}</h4>
              <ul>
                <li><span className="highlight">{t("settings.mcp.modal.benefits.localDataLabel")}</span> {t("settings.mcp.modal.benefits.localDataDesc")}</li>
                <li><span className="highlight">{t("settings.mcp.modal.benefits.externalToolsLabel")}</span> {t("settings.mcp.modal.benefits.externalToolsDesc")}</li>
                <li><span className="highlight">{t("settings.mcp.modal.benefits.extendLabel")}</span> {t("settings.mcp.modal.benefits.extendDesc")}</li>
                <li><span className="highlight">{t("settings.mcp.modal.benefits.securityLabel")}</span> {t("settings.mcp.modal.benefits.securityDesc")}</li>
              </ul>

              <h4 className="highlight">{t("settings.mcp.modal.quickStartTitle")}</h4>
              <ul>
                <li>{t("settings.mcp.modal.quickStart.enable")}</li>
                <li>{t("settings.mcp.modal.quickStart.presets")}</li>
                <li>{t("settings.mcp.modal.quickStart.custom")}</li>
                <li>{t("settings.mcp.modal.quickStart.start")}</li>
              </ul>

              <h4 className="highlight">{t("settings.mcp.modal.configurationFormatTitle")}</h4>
              <p>{t("settings.mcp.modal.configurationFormatIntro")}</p>
              <ul>
                <li><span className="highlight">name:</span> {t("settings.mcp.modal.configurationFormat.name")}</li>
                <li><span className="highlight">command:</span> {t("settings.mcp.modal.configurationFormat.command")}</li>
                <li><span className="highlight">args:</span> {t("settings.mcp.modal.configurationFormat.args")}</li>
                <li><span className="highlight">env:</span> {t("settings.mcp.modal.configurationFormat.env", { example: JSON.stringify({ API_KEY: "your_key" }) })}</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MCPSelector;
