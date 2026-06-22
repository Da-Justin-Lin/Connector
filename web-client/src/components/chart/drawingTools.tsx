import type { ReactNode } from "react";
import type { Time } from "lightweight-charts";

// A single anchor of a drawing, stored in chart space (time + price) so it
// stays put across range/interval changes and is re-projected every frame.
export interface DrawingPoint {
  time: Time;
  price: number;
}

// An anchor resolved to canvas pixels; x or y may be null when the point is
// scrolled off-screen (the tool's draw fn decides how to handle that).
export interface PixelPoint {
  x: number | null;
  y: number | null;
}

export interface Drawing {
  id: string;
  toolId: string;
  points: DrawingPoint[];
  color: string;
}

export interface ToolDrawArgs {
  ctx: CanvasRenderingContext2D;
  width: number;
  height: number;
  color: string;
  /** True for the selected drawing (and the in-progress preview): show handles. */
  selected: boolean;
  points: PixelPoint[];
  /** The drawing's anchors in chart space (time + price), for tools that need
   *  the underlying values — e.g. Measure showing the % price change. */
  anchors: DrawingPoint[];
}

export interface ToolHitArgs {
  points: PixelPoint[];
  x: number;
  y: number;
}

/**
 * A drawing tool. The registry below is the single source of truth: the
 * toolbar, the click/anchor state machine, the renderer, and hit-testing for
 * selection are all driven by these entries, so adding a tool is just one more
 * `ToolDef` (icon + anchor count + draw + hitTest).
 */
export interface ToolDef {
  id: string;
  label: string;
  /** Clicks needed to complete a drawing. 0 = a non-drawing tool (cursor). */
  anchors: number;
  icon: ReactNode;
  /** Paint the drawing given its anchors resolved to pixels. */
  draw?: (args: ToolDrawArgs) => void;
  /** Whether the mouse is over the drawing's body (for click-to-select). */
  hitTest?: (args: ToolHitArgs) => boolean;
  /** Anchor coordinates that can be typed in numerically when selected.
   *  (Currently price; the editor renders one input per anchor per field.) */
  editFields?: Array<"price">;
}

// Pixel tolerances for selecting a drawing.
export const HANDLE_RADIUS = 8;
const HIT_THRESHOLD = 6;

// Colors offered in the toolbox palette.
export const PALETTE = ["#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#a855f7", "#e5e7eb"];
export const DEFAULT_DRAW_COLOR = PALETTE[0];

// --- canvas helpers -------------------------------------------------------- #

function strokeLine(
  ctx: CanvasRenderingContext2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  color: string,
  selected: boolean,
): void {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = selected ? 2.5 : 1.5;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.restore();
}

function drawHandle(ctx: CanvasRenderingContext2D, x: number, y: number, color: string): void {
  ctx.save();
  ctx.fillStyle = color;
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(x, y, 4, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function distToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

// --- icons (16x16, inherit color via currentColor) ------------------------- #

const iconCursor = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M3 2.2l9.5 4.6-4 .9-1 4-4.5-9.5z" />
  </svg>
);

const iconTrend = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <line x1="3" y1="12.5" x2="13" y2="3.5" />
    <circle cx="3" cy="12.5" r="1.6" fill="currentColor" stroke="none" />
    <circle cx="13" cy="3.5" r="1.6" fill="currentColor" stroke="none" />
  </svg>
);

const iconHorizontal = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <line x1="2" y1="8" x2="14" y2="8" />
    <circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none" />
  </svg>
);

const iconVertical = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <line x1="8" y1="2" x2="8" y2="14" />
    <circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none" />
  </svg>
);

const iconMeasure = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <rect x="2.5" y="2.5" width="11" height="11" rx="1" strokeDasharray="2 1.5" />
    <path d="M4.5 11.5l7-7" />
    <path d="M9 4.5h2.5V7" />
  </svg>
);

// --- the registry ---------------------------------------------------------- #

export const DRAWING_TOOLS: ToolDef[] = [
  { id: "cursor", label: "Cursor", anchors: 0, icon: iconCursor },
  {
    id: "trendline",
    label: "Trend line (2 points)",
    anchors: 2,
    icon: iconTrend,
    draw: ({ ctx, color, selected, points }) => {
      const [a, b] = points;
      if (!a || !b || a.x == null || a.y == null || b.x == null || b.y == null) return;
      strokeLine(ctx, a.x, a.y, b.x, b.y, color, selected);
      if (selected) {
        drawHandle(ctx, a.x, a.y, color);
        drawHandle(ctx, b.x, b.y, color);
      }
    },
    hitTest: ({ points, x, y }) => {
      const [a, b] = points;
      if (!a || !b || a.x == null || a.y == null || b.x == null || b.y == null) return false;
      return distToSegment(x, y, a.x, a.y, b.x, b.y) <= HIT_THRESHOLD;
    },
    editFields: ["price"],
  },
  {
    id: "horizontal",
    label: "Horizontal line",
    anchors: 1,
    icon: iconHorizontal,
    draw: ({ ctx, width, color, selected, points }) => {
      const p = points[0];
      if (!p || p.y == null) return;
      strokeLine(ctx, 0, p.y, width, p.y, color, selected);
      if (selected) drawHandle(ctx, p.x ?? width / 2, p.y, color);
    },
    hitTest: ({ points, y }) => {
      const p = points[0];
      return p?.y != null && Math.abs(y - p.y) <= HIT_THRESHOLD;
    },
    editFields: ["price"],
  },
  {
    id: "vertical",
    label: "Vertical line",
    anchors: 1,
    icon: iconVertical,
    draw: ({ ctx, height, color, selected, points }) => {
      const p = points[0];
      if (!p || p.x == null) return;
      strokeLine(ctx, p.x, 0, p.x, height, color, selected);
      if (selected) drawHandle(ctx, p.x, p.y ?? height / 2, color);
    },
    hitTest: ({ points, x }) => {
      const p = points[0];
      return p?.x != null && Math.abs(x - p.x) <= HIT_THRESHOLD;
    },
  },
  {
    id: "measure",
    label: "Measure (% change)",
    anchors: 2,
    icon: iconMeasure,
    editFields: ["price"],
    draw: ({ ctx, selected, points, anchors }) => {
      const [a, b] = points;
      if (!a || !b || a.x == null || a.y == null || b.x == null || b.y == null) return;
      const x = Math.min(a.x, b.x);
      const y = Math.min(a.y, b.y);
      const w = Math.abs(b.x - a.x);
      const h = Math.abs(b.y - a.y);
      const p0 = anchors[0]?.price;
      const p1 = anchors[1]?.price;
      const up = (p1 ?? 0) >= (p0 ?? 0);
      const lineCol = up ? "#10b981" : "#ef4444";
      const fillCol = up ? "rgba(16,185,129,0.16)" : "rgba(239,68,68,0.16)";
      const meshCol = up ? "rgba(16,185,129,0.30)" : "rgba(239,68,68,0.30)";

      ctx.save();
      ctx.fillStyle = fillCol;
      ctx.fillRect(x, y, w, h);

      // Mesh: a light internal grid.
      ctx.strokeStyle = meshCol;
      ctx.lineWidth = 1;
      ctx.beginPath();
      const divs = 4;
      for (let i = 1; i < divs; i++) {
        const gx = x + (w * i) / divs;
        ctx.moveTo(gx, y);
        ctx.lineTo(gx, y + h);
        const gy = y + (h * i) / divs;
        ctx.moveTo(x, gy);
        ctx.lineTo(x + w, gy);
      }
      ctx.stroke();

      ctx.strokeStyle = lineCol;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x, y, w, h);

      if (selected) {
        drawHandle(ctx, a.x, a.y, lineCol);
        drawHandle(ctx, b.x, b.y, lineCol);
      }

      // Label: percentage price change (and absolute) of the box.
      if (p0 != null && p1 != null && p0 !== 0) {
        const pct = ((p1 - p0) / Math.abs(p0)) * 100;
        const diff = p1 - p0;
        const text = `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%   ${diff >= 0 ? "+" : ""}${diff.toFixed(2)}`;
        ctx.font = "600 12px ui-sans-serif, system-ui, sans-serif";
        ctx.textBaseline = "middle";
        ctx.textAlign = "left";
        const padX = 6;
        const bw = ctx.measureText(text).width + padX * 2;
        const bh = 20;
        const bx = x + w / 2 - bw / 2;
        const by = up ? y - bh - 4 : y + h + 4;
        const r = 4;
        ctx.fillStyle = lineCol;
        ctx.beginPath();
        ctx.moveTo(bx + r, by);
        ctx.arcTo(bx + bw, by, bx + bw, by + bh, r);
        ctx.arcTo(bx + bw, by + bh, bx, by + bh, r);
        ctx.arcTo(bx, by + bh, bx, by, r);
        ctx.arcTo(bx, by, bx + bw, by, r);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.fillText(text, bx + padX, by + bh / 2 + 0.5);
      }
      ctx.restore();
    },
    hitTest: ({ points, x, y }) => {
      const [a, b] = points;
      if (!a || !b || a.x == null || a.y == null || b.x == null || b.y == null) return false;
      return (
        x >= Math.min(a.x, b.x) &&
        x <= Math.max(a.x, b.x) &&
        y >= Math.min(a.y, b.y) &&
        y <= Math.max(a.y, b.y)
      );
    },
  },
];

export const TOOL_MAP: Record<string, ToolDef> = Object.fromEntries(
  DRAWING_TOOLS.map((t) => [t.id, t]),
);
