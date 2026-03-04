import { useEffect, useMemo, useState } from "react";
import { ReportBlueprintData, ResearchOutlineData } from "@/types/data";

interface OutlineEditorProps {
  outlineId: string;
  outline: ResearchOutlineData;
  reportBlueprint: ReportBlueprintData;
  loading?: boolean;
  onApproveExecute: () => void;
  onManualEditExecute: (manualOutline: ResearchOutlineData, manualBlueprint: ReportBlueprintData) => void;
  onAiRewrite: (instruction: string) => void;
}

export default function OutlineEditor({
  outlineId,
  outline,
  reportBlueprint,
  loading = false,
  onApproveExecute,
  onManualEditExecute,
  onAiRewrite,
}: OutlineEditorProps) {
  const initialOutlineJson = useMemo(() => JSON.stringify(outline, null, 2), [outline]);
  const initialBlueprintJson = useMemo(() => JSON.stringify(reportBlueprint, null, 2), [reportBlueprint]);
  const [outlineText, setOutlineText] = useState(initialOutlineJson);
  const [blueprintText, setBlueprintText] = useState(initialBlueprintJson);
  const [rewriteInstruction, setRewriteInstruction] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setOutlineText(initialOutlineJson);
  }, [initialOutlineJson]);

  useEffect(() => {
    setBlueprintText(initialBlueprintJson);
  }, [initialBlueprintJson]);

  const handleManualExecute = () => {
    try {
      const parsedOutline = JSON.parse(outlineText);
      const parsedBlueprint = JSON.parse(blueprintText);
      setError("");
      onManualEditExecute(parsedOutline, parsedBlueprint);
    } catch (err: any) {
      setError(`JSON parse error: ${err?.message || "invalid outline/blueprint format"}`);
    }
  };

  const handleAiRewrite = () => {
    if (!rewriteInstruction.trim()) {
      setError("Please provide rewrite instruction.");
      return;
    }
    setError("");
    onAiRewrite(rewriteInstruction.trim());
  };

  return (
    <div className="my-4 rounded-lg border border-amber-300/30 bg-amber-50/10 p-4">
      <div className="mb-2 text-sm font-semibold text-amber-200">
        Outline Draft Ready ({outlineId})
      </div>
      <div className="mb-3 text-xs text-amber-100/80">
        Confirm directly, edit manually, or ask AI to rewrite. Research will not execute until confirmed.
      </div>

      <div className="mb-3">
        <label className="mb-1 block text-xs font-semibold text-gray-200">AI rewrite instruction</label>
        <textarea
          value={rewriteInstruction}
          onChange={(e) => setRewriteInstruction(e.target.value)}
          className="h-20 w-full rounded border border-gray-600 bg-gray-900/70 p-2 text-xs text-gray-100"
          placeholder="Example: focus more on supplier patent landscape and include a dedicated cost model section."
          disabled={loading}
        />
        <button
          onClick={handleAiRewrite}
          disabled={loading}
          className="mt-2 rounded bg-sky-700 px-3 py-1 text-xs text-white hover:bg-sky-600 disabled:opacity-60"
        >
          AI Rewrite Outline
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-semibold text-gray-200">Editable Outline JSON</label>
          <textarea
            value={outlineText}
            onChange={(e) => setOutlineText(e.target.value)}
            className="h-80 w-full rounded border border-gray-600 bg-gray-900/70 p-2 font-mono text-xs text-gray-100"
            disabled={loading}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold text-gray-200">Editable Blueprint JSON</label>
          <textarea
            value={blueprintText}
            onChange={(e) => setBlueprintText(e.target.value)}
            className="h-80 w-full rounded border border-gray-600 bg-gray-900/70 p-2 font-mono text-xs text-gray-100"
            disabled={loading}
          />
        </div>
      </div>

      {error && <div className="mt-2 text-xs text-red-400">{error}</div>}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={onApproveExecute}
          disabled={loading}
          className="rounded bg-emerald-700 px-3 py-1 text-xs text-white hover:bg-emerald-600 disabled:opacity-60"
        >
          Confirm & Execute
        </button>
        <button
          onClick={handleManualExecute}
          disabled={loading}
          className="rounded bg-indigo-700 px-3 py-1 text-xs text-white hover:bg-indigo-600 disabled:opacity-60"
        >
          Manual Edit & Execute
        </button>
      </div>
    </div>
  );
}

