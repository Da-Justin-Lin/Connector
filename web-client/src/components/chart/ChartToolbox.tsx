import type { ToolDef } from "./drawingTools";

interface ChartToolboxProps {
  tools: ToolDef[];
  activeTool: string;
  onSelect: (id: string) => void;
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

/**
 * Floating drawing toolbar. Renders one button per registered tool plus the
 * shared edit actions; it is purely registry-driven, so new tools appear here
 * automatically. Designed to grow vertically (and later into grouped flyouts).
 */
export default function ChartToolbox({
  tools,
  activeTool,
  onSelect,
  onUndo,
  onClear,
  hasDrawings,
}: ChartToolboxProps) {
  const btn =
    "tap flex h-8 w-8 items-center justify-center rounded-md transition-colors";

  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-line bg-surface/90 p-1 shadow-soft backdrop-blur">
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
