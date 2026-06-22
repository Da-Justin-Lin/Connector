import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";

import {
  HANDLE_RADIUS,
  TOOL_MAP,
  type Drawing,
  type DrawingPoint,
  type PixelPoint,
} from "./drawingTools";

type AttachedChart = SeriesAttachedParameter<Time>["chart"];
type AttachedSeries = SeriesAttachedParameter<Time>["series"];

/** Result of a hit-test: the drawing under the cursor and, if a handle was
 *  hit, which anchor (else null = the body, for a whole-drawing move). */
export interface DrawingHit {
  id: string;
  anchorIndex: number | null;
}

class DrawingsPaneView implements IPrimitivePaneView {
  constructor(private readonly _source: DrawingsPrimitive) {}

  // Draw on top of the candles so lines are never hidden by the series.
  zOrder(): PrimitivePaneViewZOrder {
    return "top";
  }

  renderer(): IPrimitivePaneRenderer {
    return {
      draw: (target: CanvasRenderingTarget2D) => {
        target.useMediaCoordinateSpace((scope) => {
          const ctx = scope.context;
          const { width, height } = scope.mediaSize;
          for (const d of this._source.items()) {
            const tool = TOOL_MAP[d.toolId];
            if (!tool?.draw) continue;
            const points: PixelPoint[] = d.points.map((p) => this._source.toPixels(p));
            const selected = this._source.isSelected(d.id);
            tool.draw({ ctx, width, height, color: d.color, selected, points });
          }
        });
      },
    };
  }
}

/**
 * A series primitive that renders user drawings. It holds committed drawings
 * plus an optional in-progress preview, and re-projects every anchor from
 * (time, price) to pixels on each frame, so drawings stay anchored as the
 * chart is panned, zoomed, or switched to another range/interval.
 */
export class DrawingsPrimitive implements ISeriesPrimitive<Time> {
  private _drawings: Drawing[] = [];
  private _preview: Drawing | null = null;
  private _selectedId: string | null = null;
  private _chart?: AttachedChart;
  private _series?: AttachedSeries;
  private _requestUpdate?: () => void;
  private readonly _paneViews: DrawingsPaneView[];

  constructor() {
    this._paneViews = [new DrawingsPaneView(this)];
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this._chart = undefined;
    this._series = undefined;
    this._requestUpdate = undefined;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._paneViews;
  }

  setDrawings(drawings: Drawing[]): void {
    this._drawings = drawings;
    this._requestUpdate?.();
  }

  setPreview(preview: Drawing | null): void {
    this._preview = preview;
    this._requestUpdate?.();
  }

  setSelected(id: string | null): void {
    this._selectedId = id;
    this._requestUpdate?.();
  }

  // The preview is always rendered "selected" so its anchors show while drawing.
  isSelected(id: string): boolean {
    return id === this._selectedId || id === "preview";
  }

  items(): Drawing[] {
    return this._preview ? [...this._drawings, this._preview] : this._drawings;
  }

  toPixels(point: DrawingPoint): PixelPoint {
    const x = this._chart?.timeScale().timeToCoordinate(point.time) ?? null;
    const y = this._series?.priceToCoordinate(point.price) ?? null;
    return { x, y };
  }

  /** Topmost drawing under (x, y): a handle hit wins over a body hit, and
   *  later drawings (drawn on top) win over earlier ones. Named `pick` to
   *  avoid clashing with the primitive interface's reserved `hitTest`. */
  pick(x: number, y: number): DrawingHit | null {
    for (let i = this._drawings.length - 1; i >= 0; i--) {
      const pts = this._drawings[i].points.map((p) => this.toPixels(p));
      for (let a = 0; a < pts.length; a++) {
        const px = pts[a];
        if (px.x != null && px.y != null && Math.hypot(px.x - x, px.y - y) <= HANDLE_RADIUS) {
          return { id: this._drawings[i].id, anchorIndex: a };
        }
      }
    }
    for (let i = this._drawings.length - 1; i >= 0; i--) {
      const d = this._drawings[i];
      const tool = TOOL_MAP[d.toolId];
      if (!tool?.hitTest) continue;
      if (tool.hitTest({ points: d.points.map((p) => this.toPixels(p)), x, y })) {
        return { id: d.id, anchorIndex: null };
      }
    }
    return null;
  }
}
