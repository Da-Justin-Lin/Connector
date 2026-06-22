import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";

import { TOOL_MAP, type Drawing, type DrawingPoint, type PixelPoint } from "./drawingTools";

type AttachedChart = SeriesAttachedParameter<Time>["chart"];
type AttachedSeries = SeriesAttachedParameter<Time>["series"];

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
            tool.draw({ ctx, width, height, color: d.color, points });
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

  items(): Drawing[] {
    return this._preview ? [...this._drawings, this._preview] : this._drawings;
  }

  toPixels(point: DrawingPoint): PixelPoint {
    const x = this._chart?.timeScale().timeToCoordinate(point.time) ?? null;
    const y = this._series?.priceToCoordinate(point.price) ?? null;
    return { x, y };
  }
}
