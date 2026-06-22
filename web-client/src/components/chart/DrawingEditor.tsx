import { useEffect, useState } from "react";

import { TOOL_MAP, type Drawing } from "./drawingTools";

interface DrawingEditorProps {
  drawing: Drawing;
  onPriceChange: (anchorIndex: number, price: number) => void;
}

/**
 * Floating panel for typing the exact price of a selected drawing's anchors
 * (e.g. a horizontal line at 100.01, or each end of a trend line). Shown only
 * for tools that declare `editFields: ["price"]`.
 */
export default function DrawingEditor({ drawing, onPriceChange }: DrawingEditorProps) {
  const tool = TOOL_MAP[drawing.toolId];
  // Local text state so a half-typed value (e.g. "100.") isn't clobbered by
  // re-projection while the field is focused.
  const [drafts, setDrafts] = useState<string[]>(() => drawing.points.map((p) => String(p.price)));

  useEffect(() => {
    setDrafts(drawing.points.map((p) => String(p.price)));
  }, [drawing.id, drawing.points]);

  if (!tool?.editFields?.includes("price")) return null;

  const single = drawing.points.length === 1;

  const commit = (i: number, raw: string) => {
    const value = Number.parseFloat(raw);
    if (Number.isFinite(value)) onPriceChange(i, value);
  };

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface/90 p-2 shadow-soft backdrop-blur">
      {drawing.points.map((_, i) => (
        <label key={i} className="flex items-center gap-2 text-xs text-muted">
          <span className="w-12 shrink-0">{single ? "Price" : `Point ${i + 1}`}</span>
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            value={drafts[i] ?? ""}
            onChange={(e) => {
              const next = drafts.slice();
              next[i] = e.target.value;
              setDrafts(next);
              commit(i, e.target.value);
            }}
            className="num w-24 rounded-md border border-line bg-surface-2 px-2 py-1 text-right text-content focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </label>
      ))}
    </div>
  );
}
