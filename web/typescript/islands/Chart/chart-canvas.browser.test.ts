import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChartCanvas, type Viewport } from "./chart-canvas";

function makeViewport(): Viewport {
  const twoPi = Math.PI * 2;
  return { xMin: -twoPi, xMax: twoPi, yMin: -twoPi, yMax: twoPi };
}

function createCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.style.width = "800px";
  canvas.style.height = "600px";
  document.body.appendChild(canvas);
  Object.defineProperty(canvas, "clientWidth", { value: 800, configurable: true });
  Object.defineProperty(canvas, "clientHeight", { value: 600, configurable: true });
  canvas.setPointerCapture = () => {};
  return canvas;
}

describe("ChartCanvas", () => {
  let canvas: HTMLCanvasElement;
  let chart: ChartCanvas;

  beforeEach(() => {
    canvas = createCanvas();
  });

  afterEach(() => {
    chart?.dispose();
    canvas.remove();
  });

  it("constructs with canvas and viewport", () => {
    const vp = makeViewport();
    chart = new ChartCanvas(canvas, vp);
    expect(chart.getViewport()).toEqual(vp);
  });

  it("throws when canvas context is unavailable", () => {
    const brokenCanvas = document.createElement("canvas");
    vi.spyOn(brokenCanvas, "getContext").mockReturnValue(null);
    expect(() => new ChartCanvas(brokenCanvas, makeViewport())).toThrow(
      "Canvas 2D context not available",
    );
  });

  it("calls onViewportChange on wheel zoom", () => {
    const onViewport = vi.fn();
    const twoPi = Math.PI * 2;
    chart = new ChartCanvas(canvas, makeViewport(), onViewport);

    canvas.dispatchEvent(new WheelEvent("wheel", { deltaY: 100, clientX: 400, clientY: 300 }));

    expect(onViewport).toHaveBeenCalledOnce();
    const vp = onViewport.mock.calls[0][0] as Viewport;
    const expandedRange = twoPi * 2 * Math.exp(100 * 0.001);
    expect(vp.xMax - vp.xMin).toBeCloseTo(expandedRange, 10);
  });

  it("zooms out on negative wheel deltaY", () => {
    const onViewport = vi.fn();
    const twoPi = Math.PI * 2;
    chart = new ChartCanvas(canvas, makeViewport(), onViewport);

    canvas.dispatchEvent(new WheelEvent("wheel", { deltaY: -100, clientX: 400, clientY: 300 }));

    expect(onViewport).toHaveBeenCalledOnce();
    const vp = onViewport.mock.calls[0][0] as Viewport;
    const shrunkRange = twoPi * 2 * Math.exp(-100 * 0.001);
    expect(vp.xMax - vp.xMin).toBeCloseTo(shrunkRange, 10);
  });

  it("calls onViewportChange on pointer drag", () => {
    const onViewport = vi.fn();
    chart = new ChartCanvas(canvas, makeViewport(), onViewport);

    canvas.dispatchEvent(
      new PointerEvent("pointerdown", { clientX: 400, clientY: 300, pointerId: 1 }),
    );
    canvas.dispatchEvent(new PointerEvent("pointermove", { clientX: 410, clientY: 310 }));
    canvas.dispatchEvent(new PointerEvent("pointerup", { clientX: 410, clientY: 310 }));

    expect(onViewport).toHaveBeenCalled();
  });

  it("does not call onViewportChange on pointermove without pointerdown", () => {
    const onViewport = vi.fn();
    chart = new ChartCanvas(canvas, makeViewport(), onViewport);

    canvas.dispatchEvent(new PointerEvent("pointermove", { clientX: 410, clientY: 310 }));

    expect(onViewport).not.toHaveBeenCalled();
  });

  it("shows tooltip when cursor is near curve data", () => {
    const onTooltip = vi.fn();
    chart = new ChartCanvas(canvas, makeViewport(), undefined, onTooltip);

    chart.setData([
      [0, 0],
      [1, 1],
      [2, 2],
    ]);

    canvas.dispatchEvent(new PointerEvent("pointermove", { clientX: 400, clientY: 300 }));

    expect(onTooltip).toHaveBeenCalledWith({
      x: 0,
      y: 0,
      canvasX: 400,
      canvasY: 300,
    });
  });

  it("clears tooltip on pointerleave", () => {
    const onTooltip = vi.fn();
    chart = new ChartCanvas(canvas, makeViewport(), undefined, onTooltip);

    chart.setData([[0, 0]]);

    canvas.dispatchEvent(new PointerEvent("pointerleave", { clientX: 400, clientY: 300 }));

    expect(onTooltip).toHaveBeenCalledWith(null);
  });

  it("disposes event listeners and resize observer", () => {
    const onViewport = vi.fn();
    chart = new ChartCanvas(canvas, makeViewport(), onViewport);
    chart.dispose();

    canvas.dispatchEvent(new WheelEvent("wheel", { deltaY: 100, clientX: 400, clientY: 300 }));

    expect(onViewport).not.toHaveBeenCalled();
  });

  it("renders without throwing for valid data", () => {
    chart = new ChartCanvas(canvas, makeViewport());
    chart.setData([[0, 0]]);

    expect(canvas.width).toBeGreaterThan(0);
    expect(canvas.height).toBeGreaterThan(0);
  });

  it("handles empty data set", () => {
    chart = new ChartCanvas(canvas, makeViewport());
    chart.setData([]);

    expect(chart.getViewport()).toBeDefined();
  });
});
