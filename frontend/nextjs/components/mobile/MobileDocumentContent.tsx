import React from "react";
import LoadingDots from "@/components/LoadingDots";
import ChatInput from "@/components/ResearchBlocks/elements/ChatInput";
import { ResearchResults } from "@/components/ResearchResults";
import { ChatBoxSettings, Data } from "@/types/data";
import { useTranslations } from "next-intl";

interface MobileDocumentContentProps {
  orderedData: Data[];
  answer: string;
  allLogs: any[];
  chatBoxSettings: ChatBoxSettings;
  loading: boolean;
  isStopped: boolean;
  chatPromptValue: string;
  setChatPromptValue: React.Dispatch<React.SetStateAction<string>>;
  handleChat: (message: string) => void;
  isProcessingChat?: boolean;
  onNewResearch?: () => void;
  currentResearchId?: string;
  onShareClick?: () => void;
}

export default function MobileDocumentContent({
  orderedData,
  answer,
  allLogs,
  chatBoxSettings,
  loading,
  isStopped,
  chatPromptValue,
  setChatPromptValue,
  handleChat,
  isProcessingChat = false,
  onNewResearch,
  currentResearchId,
  onShareClick,
}: MobileDocumentContentProps) {
  const t = useTranslations();
  const isBusy = loading || isProcessingChat;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-gradient-to-b from-gray-900 to-gray-950">
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="space-y-3">
          <ResearchResults
            orderedData={orderedData}
            answer={answer}
            allLogs={allLogs}
            chatBoxSettings={chatBoxSettings}
            handleClickSuggestion={() => {}}
            currentResearchId={currentResearchId}
            isProcessingChat={isProcessingChat}
            onShareClick={onShareClick}
          />
          {isBusy && (
            <div className="flex justify-center py-2">
              <LoadingDots />
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-gray-800/70 bg-gray-900/80 px-3 py-3">
        {!isStopped ? (
          <ChatInput
            promptValue={chatPromptValue}
            setPromptValue={setChatPromptValue}
            handleSubmit={handleChat}
            disabled={isBusy}
          />
        ) : (
          <div className="rounded-xl border border-gray-700/50 bg-gray-800/60 p-3 text-center text-sm text-gray-300">
            {t("chat.researchStopped")}
            {onNewResearch && (
              <button
                onClick={onNewResearch}
                className="ml-2 font-medium text-teal-400 hover:text-teal-300 hover:underline"
              >
                {t("common.startNewResearch")}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
