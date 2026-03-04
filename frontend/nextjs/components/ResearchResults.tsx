import React from 'react';
import Question from './ResearchBlocks/Question';
import Report from './ResearchBlocks/Report';
import Sources from './ResearchBlocks/Sources';
import ImageSection from './ResearchBlocks/ImageSection';
import SubQuestions from './ResearchBlocks/elements/SubQuestions';
import LogsSection from './ResearchBlocks/LogsSection';
import AccessReport from './ResearchBlocks/AccessReport';
import OutlineEditor from './ResearchBlocks/OutlineEditor';
import { preprocessOrderedData } from '../utils/dataProcessing';
import { Data } from '../types/data';

interface ResearchResultsProps {
  orderedData: Data[];
  answer: string;
  allLogs: any[];
  chatBoxSettings: any;
  handleClickSuggestion: (value: string) => void;
  currentResearchId?: string;
  isProcessingChat?: boolean;
  onShareClick?: () => void;
  planningLoading?: boolean;
  onApproveOutlineExecute?: () => void;
  onManualOutlineExecute?: (manualOutline: any, manualBlueprint: any) => void;
  onAiRewriteOutline?: (instruction: string) => void;
}

export const ResearchResults: React.FC<ResearchResultsProps> = ({
  orderedData,
  answer,
  allLogs,
  chatBoxSettings,
  handleClickSuggestion,
  currentResearchId,
  isProcessingChat = false,
  onShareClick,
  planningLoading = false,
  onApproveOutlineExecute,
  onManualOutlineExecute,
  onAiRewriteOutline,
}) => {
  const groupedData = preprocessOrderedData(orderedData);
  const pathData = groupedData.find(data => data.type === 'path');
  const initialQuestion = groupedData.find(data => data.type === 'question');
  const latestOutline = [...groupedData]
    .reverse()
    .find(data => data.type === 'outline_updated' || data.type === 'outline_draft');

  const chatComponents = groupedData
    .filter(data => {
      if (data.type === 'question' && data === initialQuestion) {
        return false;
      }
      return (data.type === 'question' || data.type === 'chat');
    })
    .map((data, index) => {
      if (data.type === 'question') {
        return <Question key={`question-${index}`} question={data.content} />;
      } else {
        return <Report key={`chat-${index}`} answer={data.content} />;
      }
    });

  const sourceComponents = groupedData
    .filter(data => data.type === 'sourceBlock')
    .map((data, index) => (
      <Sources key={`sourceBlock-${index}`} sources={data.items}/>
    ));

  const imageComponents = groupedData
    .filter(data => data.type === 'imagesBlock')
    .map((data, index) => (
      <ImageSection key={`images-${index}-${data.metadata?.length || 0}`} metadata={data.metadata} />
    ));

  const initialReport = groupedData.find(data => data.type === 'reportBlock');
  const finalReport = groupedData
    .filter(data => data.type === 'reportBlock')
    .pop();
  const subqueriesComponent = groupedData.find(data => data.content === 'subqueries');

  return (
    <>
      {initialQuestion && <Question question={initialQuestion.content} />}
      {latestOutline && !pathData && onApproveOutlineExecute && onManualOutlineExecute && onAiRewriteOutline && (
        <OutlineEditor
          outlineId={latestOutline.outline_id}
          outline={latestOutline.outline}
          reportBlueprint={latestOutline.report_blueprint}
          loading={planningLoading}
          onApproveExecute={onApproveOutlineExecute}
          onManualEditExecute={onManualOutlineExecute}
          onAiRewrite={onAiRewriteOutline}
        />
      )}
      {orderedData.length > 0 && <LogsSection logs={allLogs} />}
      {subqueriesComponent && (
        <SubQuestions
          metadata={subqueriesComponent.metadata}
          handleClickSuggestion={handleClickSuggestion}
        />
      )}
      {sourceComponents}
      {imageComponents}
      {finalReport && <Report answer={finalReport.content} researchId={currentResearchId} />}
      {pathData && <AccessReport accessData={pathData.output} report={answer} chatBoxSettings={chatBoxSettings} onShareClick={onShareClick} />}
      {chatComponents}
    </>
  );
}; 
