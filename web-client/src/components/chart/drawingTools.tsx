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
  points: PixelPoint[];
}

/**
 * A drawing tool. The registry below is the single source of truth: the
 * toolbar, the click/anchor state machine, and the canvas renderer are all
 * driven by these entries, so adding a tool is just one more `ToolDef`.
 */
export interface ToolDef {
  id: string;
  label: string;
  /** Clicks needed to complete a drawing. 0 = a non-drawing tool (cursor). */
  anchors: number;
  icon: ReactNode;
  /** Paint the drawing given its anchors resolved to pixels. */
  draw?: (args: ToolDrawArgs) => void;
}

// --- canvas helpers -------------------------------------------------------- #

function strokeLine(
  ctx: CanvasRenderingContext2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  color: string,
): void {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
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
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(x, y, 3.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
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

// --- the registry ---------------------------------------------------------- #

export const DRAWING_TOOLS: ToolDef[] = [
  { id: "cursor", label: "Cursor", anchors: 0, icon: iconCursor },
  {
    id: "trendline",
    label: "Trend line (2 points)",
    anchors: 2,
    icon: iconTrend,
    draw: ({ ctx, color, points }) => {
      const [a, b] = points;
      if (!a || !b || a.x == null || a.y == null || b.x == null || b.y == null) return;
      strokeLine(ctx, a.x, a.y, b.x, b.y, color);
      drawHandle(ctx, a.x, a.y, color);
      drawHandle(ctx, b.x, b.y, color);
    },
  },
  {
    id: "horizontal",
    label: "Horizontal line",
    anchors: 1,
    icon: iconHorizontal,
    draw: ({ ctx, width, color, points }) => {
      const p = points[0];
      if (!p || p.y == null) return;
      strokeLine(ctx, 0, p.y, width, p.y, color);
    },
  },
  {
    id: "vertical",
    label: "Vertical line",
    anchors: 1,
    icon: iconVertical,
    draw: ({ ctx, height, color, points }) => {
      const p = points[0];
      if (!p || p.x == null) return;
      strokeLine(ctx, p.x, 0, p.x, height, color);
    },
  },
];

export const TOOL_MAP: Record<string, ToolDef> = Object.fromEntries(
  DRAWING_TOOLS.map((t) => [t.id, t]),
);

export const DEFAULT_DRAW_COLOR = "#3b82f6";
