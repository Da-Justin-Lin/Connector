"use client";

import { useState } from "react";

import { PALETTE, type ToolDef } from "./drawingTools";

interface ChartToolboxProps {
  tools: ToolDef[];
  activeTool: string;
  onSelect: (id: string) => void;
  color: string;
  onColorChange: (color: string) => void;
  onDelete: () => void;
  hasSelection: boolean;
  onUndo: () => void;
  onClear: () => void;
  hasDrawings: boolean;
}

const iconUndo = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d="M6 4L3 7l3 3" />
    <path d="M3 7h6.5a3.5 3.5 0 010 7H6" />
  </svg>
);

const iconTrash = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d="M3 4.5h10M6.5 4.5V3h3v1.5M5 4.5l.6 8h4.8l.6-8" />
  </svg>
);

const iconDelete = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <circle cx="8" cy="8" r="6" />
    <line x1="5.5" y1="5.5" x2="10.5" y2="10.5" />
    <line x1="10.5" y1="5.5" x2="5.5" y2="10.5" />
  </svg>
);

// Collapsed-state handle (pencil) and the collapse chevron.
const iconPencil = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d="M11 2.5l2.5 2.5L6 12.5l-3 .5.5-3z" />
  </svg>
);

const iconChevronUp = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d="M4 10l4-4 4 4" />
  </svg>
);

/**
 * Floating drawing toolbar. Renders one button per registered tool plus the
 * shared edit actions; it is purely registry-driven, so new tools appear here
 * automatically. Designed to grow vertically (and later into grouped flyouts).
 */
export default function ChartToolbox({
  tools,
  activeTool,
  onSelect,
  color,
  onColorChange,
  onDelete,
  hasSelection,
  onUndo,
  onClear,
  hasDrawings,
}: ChartToolboxProps) {
  const [expanded, setExpanded] = useState(false);
  const btn =
    "tap flex h-8 w-8 items-center justify-center rounded-md transition-colors";

  // Collapsed: a single handle showing the active tool's icon. Click to expand.
  if (!expanded) {
    const activeIcon = tools.find((t) => t.id === activeTool)?.icon ?? iconPencil;
    return (
      <button
        type="button"
        title="Drawing tools"
        aria-label="Show drawing tools"
        aria-expanded={false}
        onClick={() => setExpanded(true)}
        className="tap flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-surface/90 text-muted shadow-soft backdrop-blur transition-colors hover:text-content"
      >
        {activeIcon}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-line bg-surface/90 p-1 shadow-soft backdrop-blur">
      <button
        type="button"
        title="Collapse toolbar"
        aria-label="Collapse toolbar"
        aria-expanded
        onClick={() => setExpanded(false)}
        className={`${btn} text-muted hover:bg-surface-2 hover:text-content`}
      >
        {iconChevronUp}
      </button>

      <div className="my-0.5 h-px bg-line" />

      {tools.map((t) => {
        const active = activeTool === t.id;
        return (
          <button
            key={t.id}
            type="button"
            title={t.label}
            aria-label={t.label}
            aria-pressed={active}
            onClick={() => onSelect(t.id)}
            className={`${btn} ${
              active ? "bg-brand text-white" : "text-muted hover:bg-surface-2 hover:text-content"
            }`}
          >
            {t.icon}
          </button>
        );
      })}

      <div className="my-0.5 h-px bg-line" />

      {/* Color: sets the color for new drawings, or recolors the selected one. */}
      <div className="grid grid-cols-2 gap-1 px-0.5 py-0.5">
        {PALETTE.map((c) => (
          <button
            key={c}
            type="button"
            title={hasSelection ? "Recolor selection" : "Drawing color"}
            aria-label={`Color ${c}`}
            aria-pressed={color === c}
            onClick={() => onColorChange(c)}
            className={`tap h-4 w-4 rounded-full border transition-transform hover:scale-110 ${
              color === c ? "border-content ring-1 ring-content" : "border-line"
            }`}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>

      <div className="my-0.5 h-px bg-line" />

      <button
        type="button"
        title="Delete selected drawing"
        aria-label="Delete selected drawing"
        onClick={onDelete}
        disabled={!hasSelection}
        className={`${btn} text-muted hover:bg-surface-2 hover:text-down disabled:opacity-30 disabled:hover:bg-transparent`}
      >
        {iconDelete}
      </button>

      <button
        type="button"
        title="Remove last drawing"
        aria-label="Remove last drawing"
        onClick={onUndo}
        disabled={!hasDrawings}
        className={`${btn} text-muted hover:bg-surface-2 hover:text-content disabled:opacity-30 disabled:hover:bg-transparent`}
      >
        {iconUndo}
      </button>
      <button
        type="button"
        title="Clear all drawings"
        aria-label="Clear all drawings"
        onClick={onClear}
        disabled={!hasDrawings}
        className={`${btn} text-muted hover:bg-surface-2 hover:text-down disabled:opacity-30 disabled:hover:bg-transparent`}
      >
        {iconTrash}
      </button>
    </div>
  );
}
