import { createEffect, createSignal, onSettled, Show } from "solid-js";

import { ChartCanvas, type TooltipPoint, type Viewport } from "./chart-canvas";
import { compileExpression, sampleExpression } from "./math-parser";

import "./chart.css";

interface Props {
  title?: unknown;
  formula?: unknown;
  "hide-input"?: unknown;
  "disable-drag"?: unknown;
  "x-min"?: unknown;
  "x-max"?: unknown;
  "y-min"?: unknown;
  "y-max"?: unknown;
}

const RANGE_DEFAULT = Math.PI * 2;

function toNumber(data: unknown): number | null {
  if (typeof data === "number") {
    return data;
  }
  if (typeof data === "string") {
    return Number.isNaN(Number(data)) ? null : Number(data);
  }
  return null;
}

export function ECharts(props: Readonly<Props>) {
  const [source, setSource] = createSignal(() => {
    if (typeof props.formula === "number") {
      return props.formula.toString();
    }
    if (typeof props.formula === "string") {
      return props.formula;
    }
    return "sin(x)";
  });
  const [tooltip, setTooltip] = createSignal<TooltipPoint | null>(null);
  const [error, setError] = createSignal("");
  let container!: HTMLCanvasElement;
  let canvas: ChartCanvas;

  const title = () => (typeof props.title === "string" ? props.title.trim() : "");
  const disablePanAndZoom = () => {
    const value = props["disable-drag"];
    if (typeof value === "string") {
      return value.toLowerCase() === "true";
    } else if (typeof value === "boolean") {
      return value;
    }
    return false;
  };

  const showError = (reason: unknown) => {
    canvas.setData([]);
    setTooltip(null);
    setError(reason instanceof Error ? reason.message : "Invalid formula");
  };

  const updateCurve = (viewport: Viewport, formula = source()) => {
    try {
      const points = sampleExpression(
        compileExpression(formula),
        viewport.xMin,
        viewport.xMax,
        Math.ceil(container.clientWidth),
      );
      canvas.setData(points);
      setError("");
    } catch (reason) {
      showError(reason);
    }
  };

  // TODO: input validation
  onSettled(() => {
    // init props state
    const nextXRange: [number, number] = [
      toNumber(props["x-min"]) ?? -RANGE_DEFAULT,
      toNumber(props["x-max"]) ?? RANGE_DEFAULT,
    ];
    const nextYRange: [number, number] = [
      toNumber(props["y-min"]) ?? -RANGE_DEFAULT,
      toNumber(props["y-max"]) ?? RANGE_DEFAULT,
    ];

    // init canvas
    canvas = new ChartCanvas(
      container,
      {
        xMin: nextXRange[0],
        xMax: nextXRange[1],
        yMin: nextYRange[0],
        yMax: nextYRange[1],
      },
      updateCurve,
      setTooltip,
      disablePanAndZoom(),
    );
    updateCurve(canvas.getViewport(), source());

    return () => {
      canvas?.dispose();
    };
  });

  createEffect(
    source,
    (formula) => {
      if (!canvas) {
        return;
      }

      const viewport = canvas.getViewport();
      updateCurve(viewport, formula);
    },
    // in solid 2, createEffect is prior to onSettled.
    // defer it at the first run.
    { defer: true },
  );

  // TODO: reset button
  return (
    <section class="md-chart" data-caption={title()}>
      <Show when={props["hide-input"] !== true && props["hide-input"] !== "true"}>
        <label>
          <span>f(x)=</span>
          <input
            value={source()}
            onInput={(e) => setSource(e.currentTarget.value)}
            spellcheck="false"
          />
        </label>
      </Show>

      {error() && <p role="alert">{error()}</p>}

      <div style={{ position: "relative" }}>
        <canvas
          ref={(e) => (container = e)}
          style={{
            width: "100%",
            height: "28rem",
            cursor: disablePanAndZoom() ? "default" : "crosshair",
            display: "block",
          }}
        />

        <Show when={tooltip()}>
          {(point) => (
            <output
              style={{
                position: "absolute",
                left: `${point().canvasX}px`,
                top: `${point().canvasY}px`,
                transform: "translate(-50%, calc(-100% - 10px))",
                padding: "0.35rem 0.5rem",
                "border-radius": "0.35rem",
                background: "rgba(15, 23, 42, 0.9)",
                color: "white",
                "font-size": "0.75rem",
                "pointer-events": "none",
                "white-space": "nowrap",
              }}
            >
              x={Number(point().x.toPrecision(6))}, y={Number(point().y.toPrecision(6))}
            </output>
          )}
        </Show>
      </div>
    </section>
  );
}
