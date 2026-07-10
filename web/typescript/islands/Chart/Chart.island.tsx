import type { EvalFunction } from "mathjs/number";
import { createEffect, createSignal, onCleanup, onMount, Show } from "solid-js";

import { ChartCanvas, type TooltipPoint, type Viewport } from "./chart-canvas";
import { compileExpression, sampleExpression } from "./math-parser";

interface Props {
  formula?: unknown;
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
  const [source, setSource] = createSignal("sin(x)");
  const [evaluate, setEvaluate] = createSignal<EvalFunction>(compileExpression(source()));
  // TODO: merge there two to Viewport type
  const [xRange, setXRange] = createSignal([-RANGE_DEFAULT, RANGE_DEFAULT]);
  const [yRange, setYRange] = createSignal([-RANGE_DEFAULT, RANGE_DEFAULT]);
  const [tooltip, setTooltip] = createSignal<TooltipPoint | null>(null);
  const [error, setError] = createSignal("");
  let container!: HTMLCanvasElement;
  let canvas: ChartCanvas;

  const updateCurve = (viewport: Viewport) => {
    try {
      const points = sampleExpression(
        evaluate(),
        viewport.xMin,
        viewport.xMax,
        Math.ceil(container.clientWidth),
      );
      canvas.setData(points);
      setError("");
    } catch (e) {
      canvas.setData([]);
      setTooltip(null);
      setError(e instanceof Error ? e.message : "Invalid formula");
    }
  };

  // TODO: input validation
  onMount(() => {
    // init props state
    setXRange([
      toNumber(props["x-min"]) ?? -RANGE_DEFAULT,
      toNumber(props["x-max"]) ?? RANGE_DEFAULT,
    ]);
    setYRange([
      toNumber(props["y-min"]) ?? -RANGE_DEFAULT,
      toNumber(props["y-max"]) ?? RANGE_DEFAULT,
    ]);
    let formula: string;
    if (typeof props.formula === "number") {
      formula = props.formula.toString();
    } else if (typeof props.formula === "string") {
      formula = props.formula;
    } else {
      formula = "sin(x)";
    }
    setSource(formula);

    // init canvas
    canvas = new ChartCanvas(
      container,
      {
        xMin: xRange()[0],
        xMax: xRange()[1],
        yMin: yRange()[0],
        yMax: yRange()[1],
      },
      updateCurve,
      setTooltip,
    );
  });

  createEffect(() => {
    // registry this to solid effect
    source();

    if (!canvas) {
      return;
    }

    const viewport = canvas.getViewport();
    setEvaluate(compileExpression(source()));
    updateCurve(viewport);
  });

  onCleanup(() => {
    canvas?.dispose();
  });

  // TODO: reset button
  return (
    <section>
      <label>
        <span>f(x)=</span>
        <input
          value={source()}
          onInput={(e) => setSource(e.currentTarget.value)}
          spellcheck={false}
        />
      </label>

      {error() && <p role="alert">{error()}</p>}

      <div style={{ position: "relative" }}>
        <canvas
          ref={(e) => (container = e)}
          style={{ width: "100%", height: "28rem", cursor: "crosshair", display: "block" }}
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
