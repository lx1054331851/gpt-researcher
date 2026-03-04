export interface BaseData {
  type: string;
}

export interface BasicData extends BaseData {
  type: 'basic';
  content: string;
}

export interface LanggraphButtonData extends BaseData {
  type: 'langgraphButton';
  link: string;
}

export interface DifferencesData extends BaseData {
  type: 'differences';
  content: string;
  output: string;
}

export interface QuestionData extends BaseData {
  type: 'question';
  content: string;
}

export interface ChatData extends BaseData {
  type: 'chat';
  content: string;
  metadata?: any; // For storing search results and other contextual information
}

export interface OutlineSectionData {
  id: string;
  title: string;
  intent: string;
  key_questions: string[];
  stage: "foundation" | "evidence" | "judgement";
  priority: number;
  required: boolean;
}

export interface ResearchOutlineData {
  outline_id: string;
  query: string;
  objective: string;
  scope?: string;
  workstreams?: Array<{
    id: string;
    title: string;
    intent: string;
    deliverable?: string;
  }>;
  evidence_requirements?: string[];
  deliverables?: string[];
  risk_controls?: string[];
  must_answer_questions?: string[];
  audience?: string | null;
  constraints: string[];
  sections: OutlineSectionData[];
}

export interface SectionSpecData {
  id: string;
  title: string;
  purpose: string;
  stage: "foundation" | "evidence" | "judgement";
  required_evidence_types: string[];
  min_citations: number;
  must_include?: string[];
}

export interface ReportBlueprintData {
  section_order: string[];
  section_specs: SectionSpecData[];
  narrative_strategy: string;
  citation_policy?: Record<string, any>;
  output_constraints?: string[];
}

export interface OutlineDraftData extends BaseData {
  type: 'outline_draft';
  content?: string;
  outline_id: string;
  outline: ResearchOutlineData;
  report_blueprint: ReportBlueprintData;
  report_style?: "strategic_report" | "consulting_brief";
  source_policy?: "strict_tier" | "medium_tier" | "broad_collect";
}

export interface OutlineUpdatedData extends BaseData {
  type: 'outline_updated';
  content?: string;
  outline_id: string;
  outline: ResearchOutlineData;
  report_blueprint: ReportBlueprintData;
  report_style?: "strategic_report" | "consulting_brief";
  source_policy?: "strict_tier" | "medium_tier" | "broad_collect";
}

export interface PathData extends BaseData {
  type: 'path';
  content?: string;
  output?: Record<string, any>;
}

export type Data =
  | BasicData
  | LanggraphButtonData
  | DifferencesData
  | QuestionData
  | ChatData
  | OutlineDraftData
  | OutlineUpdatedData
  | PathData;

export interface MCPConfig {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface ChatBoxSettings {
  report_type: string;
  report_source: string;
  tone: string;
  report_language: string;
  report_style: "strategic_report" | "consulting_brief";
  source_policy: "strict_tier" | "medium_tier" | "broad_collect";
  word_fonts?: string[];
  domains: string[];
  defaultReportType: string;
  layoutType: string;
  mcp_enabled: boolean;
  mcp_configs: MCPConfig[];
  mcp_strategy?: string;
}

export interface Domain {
  value: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
  metadata?: any; // For storing search results and other contextual information
}

export interface ResearchHistoryItem {
  id: string;
  question: string;
  answer: string;
  timestamp: number;
  orderedData: Data[];
  chatMessages?: ChatMessage[];
} 

export type AdaptiveResearchStage =
  | 'idle'
  | 'planning'
  | 'await_outline_approval'
  | 'executing'
  | 'completed';
