import { fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mockCanvas = vi.hoisted(() => ({
  setDataCalls: [] as Array<Array<[number, number | null]>>,
  disposeCount: 0,
  viewport: undefined as unknown,
  viewportCallback: undefined as ((viewport: unknown) => void) | undefined,
  tooltipCallback: undefined as ((point: unknown) => void) | undefined,
  reset() {
    this.setDataCalls = [];
    this.disposeCount = 0;
    this.viewport = undefined;
    this.viewportCallback = undefined;
    this.tooltipCallback = undefined;
  },
}));

vi.mock("./chart-canvas", () => ({
  ChartCanvas: class {
    setData(data: Array<[number, number | null]>) {
      mockCanvas.setDataCalls.push(data);
    }
    getViewport() {
      return { xMin: -6.28, xMax: 6.28, yMin: -6.28, yMax: 6.28 };
    }
    dispose() {
      mockCanvas.disposeCount++;
    }
    constructor(
      _canvas: HTMLCanvasElement,
      viewport: unknown,
      onViewportChange?: (vp: unknown) => void,
      onTooltipChange?: (point: unknown) => void,
    ) {
      mockCanvas.viewport = viewport;
      mockCanvas.viewportCallback = onViewportChange;
      mockCanvas.tooltipCallback = onTooltipChange;
    }
  },
}));

let shouldFailSample = false;

vi.mock("./math-parser", () => ({
  compileExpression(source: string) {
    if (source === "invalid") {
      throw new Error("Mock compile error");
    }
    return { evaluate: () => 0 };
  },
  sampleExpression(
    _evaluate: unknown,
    _min: number,
    _max: number,
    _count: number,
  ): Array<[number, number | null]> {
    if (shouldFailSample) {
      throw new Error("Mock sample error");
    }
    return [[0, 0]];
  },
}));

import { ECharts } from "./Chart.island";

beforeEach(() => {
  mockCanvas.reset();
  shouldFailSample = false;
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders formula input and canvas", () => {
  render(() => <ECharts />);
  expect(screen.getByRole("textbox")).toHaveValue("sin(x)");
  expect(screen.getByText("f(x)=")).toBeInTheDocument();
  expect(document.querySelector("canvas")).toBeInTheDocument();
});

test("renders no error on valid initial formula", () => {
  render(() => <ECharts />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("renders no tooltip initially", () => {
  render(() => <ECharts />);
  expect(document.querySelector("output")).not.toBeInTheDocument();
});

test("calls canvas.setData on mount", () => {
  render(() => <ECharts />);
  expect(mockCanvas.setDataCalls.length).toBeGreaterThanOrEqual(1);
});

test("calls canvas.dispose on cleanup", () => {
  const { unmount } = render(() => <ECharts />);
  unmount();
  expect(mockCanvas.disposeCount).toBe(1);
});

test("updates when formula input changes", () => {
  render(() => <ECharts />);
  const beforeCount = mockCanvas.setDataCalls.length;

  const input = screen.getByRole("textbox");
  fireEvent.input(input, { target: { value: "cos(x)" } });

  expect(mockCanvas.setDataCalls.length).toBeGreaterThan(beforeCount);
});

test("shows error when sampleExpression throws", () => {
  shouldFailSample = true;
  render(() => <ECharts />);
  expect(screen.getByRole("alert")).toHaveTextContent("Mock sample error");
});

test("shows error when formula compilation throws", () => {
  render(() => <ECharts />);

  fireEvent.input(screen.getByRole("textbox"), { target: { value: "invalid" } });

  expect(screen.getByRole("alert")).toHaveTextContent("Mock compile error");
});

test("keeps a compilation error when the viewport changes", () => {
  render(() => <ECharts />);

  fireEvent.input(screen.getByRole("textbox"), { target: { value: "invalid" } });
  expect(screen.getByRole("alert")).toBeInTheDocument();

  mockCanvas.viewportCallback!({ xMin: -5, xMax: 5, yMin: -1, yMax: 1 });

  expect(screen.getByRole("alert")).toHaveTextContent("Mock compile error");
});

test("clears a compilation error after fixing formula", () => {
  render(() => <ECharts />);

  const input = screen.getByRole("textbox");
  fireEvent.input(input, { target: { value: "invalid" } });
  expect(screen.getByRole("alert")).toBeInTheDocument();

  fireEvent.input(input, { target: { value: "cos(x)" } });

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("renders tooltip when setTooltip callback is called", () => {
  render(() => <ECharts />);

  mockCanvas.tooltipCallback!({ x: 1.23456, y: 2.34567, canvasX: 100, canvasY: 50 });

  expect(document.querySelector("output")).toBeInTheDocument();
  expect(document.querySelector("output")!.textContent).toContain("1.23456");
  expect(document.querySelector("output")!.textContent).toContain("2.34567");
});

test("hides tooltip when setTooltip callback is called with null", () => {
  render(() => <ECharts />);

  mockCanvas.tooltipCallback!({ x: 1, y: 2, canvasX: 100, canvasY: 50 });
  expect(document.querySelector("output")).toBeInTheDocument();

  mockCanvas.tooltipCallback!(null);
  expect(document.querySelector("output")).not.toBeInTheDocument();
});

test("initializes with props values", () => {
  render(() => <ECharts formula="cos(x)" x-min={-5} x-max={5} y-min={-1} y-max={1} />);

  expect(screen.getByRole("textbox")).toHaveValue("cos(x)");
  expect(mockCanvas.viewport).toEqual({ xMin: -5, xMax: 5, yMin: -1, yMax: 1 });
  expect(mockCanvas.setDataCalls.length).toBeGreaterThanOrEqual(1);
});

test("falls back to default formula when prop is missing", () => {
  render(() => <ECharts />);
  expect(screen.getByRole("textbox")).toHaveValue("sin(x)");
});

test("falls back to default formula when prop is neither string nor number", () => {
  render(() => <ECharts formula={{ invalid: true } as unknown} />);
  expect(screen.getByRole("textbox")).toHaveValue("sin(x)");
});

test("tooltip output is positioned absolutely", () => {
  render(() => <ECharts />);

  mockCanvas.tooltipCallback!({ x: 1, y: 2, canvasX: 100, canvasY: 50 });

  const output = document.querySelector("output")!;
  expect(output.style.position).toBe("absolute");
  expect(output.style.left).toBe("100px");
  expect(output.style.top).toBe("50px");
});
