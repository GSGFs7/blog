export interface Viewport {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export type ViewportChangeCallback = (viewport: Viewport) => void;

export interface TooltipPoint {
  x: number;
  y: number;
  canvasX: number;
  canvasY: number;
}

export type TooltipChangeCallback = (point: TooltipPoint | null) => void;

// TODO: touch support
export class ChartCanvas {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private readonly resizeObserver: ResizeObserver;

  // --- data ---
  private data: Array<[number, number | null]> = [];

  // --- canvas ---
  private readonly viewport: Viewport;
  // width & height has inited in `onResize()`
  private width!: number;
  private height!: number;

  // --- user interaction ---
  private dragging: boolean = false;
  private lastPointerX: number = 0;
  private lastPointerY: number = 0;
  private animationFrame: number | null = null;

  // --- listener ---
  private readonly boundPointerDown = (e: PointerEvent) => this.handlePointerDown(e);
  private readonly boundPointerUp = (e: PointerEvent) => this.handlePointerUp(e);
  private readonly boundPointerMove = (e: PointerEvent) => this.handlePointerMove(e);
  private readonly boundPointerLeave = (e: PointerEvent) => this.handlePointerLeave(e);
  private readonly boundWheel = (e: WheelEvent) => this.handleWheel(e);

  constructor(
    canvaRef: HTMLCanvasElement,
    viewport: Viewport,
    private readonly onViewportChange?: ViewportChangeCallback,
    private readonly onTooltipChange?: TooltipChangeCallback,
  ) {
    const ctx = canvaRef.getContext("2d");
    if (!ctx) {
      throw new Error("Canvas 2D context not available");
    }

    this.canvas = canvaRef;
    this.ctx = ctx;
    this.viewport = viewport;

    // bind resize observer
    this.resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        this.onResize(width, height);
      }
    });
    this.resizeObserver.observe(this.canvas);
    this.onResize(canvaRef.clientWidth, canvaRef.clientHeight); // init

    this.canvas.addEventListener("pointerdown", this.boundPointerDown);
    this.canvas.addEventListener("pointerup", this.boundPointerUp);
    this.canvas.addEventListener("pointermove", this.boundPointerMove);
    this.canvas.addEventListener("pointerleave", this.boundPointerLeave);
    this.canvas.addEventListener("wheel", this.boundWheel);
  }

  setData(data: Array<[number, number | null]>) {
    this.data = data;
    this.requestDraw();
  }

  getViewport(): Viewport {
    return this.viewport;
  }

  dispose() {
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
    }

    this.resizeObserver.disconnect();
    this.canvas.removeEventListener("pointerdown", this.boundPointerDown);
    this.canvas.removeEventListener("pointermove", this.boundPointerMove);
    this.canvas.removeEventListener("pointerup", this.boundPointerUp);
    this.canvas.removeEventListener("pointerleave", this.boundPointerLeave);
    this.canvas.removeEventListener("wheel", this.boundWheel);
  }

  // --- coordinate transform ---
  // scaling real data to the small canvas widow
  // note that, y-axis is from top to bottom. origin is upper left

  private worldToScreen(x: number, y: number): [number, number] {
    const { xMin, xMax, yMin, yMax } = this.viewport;
    // normalize the real data -> [0, 1]
    const normalizedX = (x - xMin) / (xMax - xMin);
    const normalizedY = (yMax - y) / (yMax - yMin); // reversal y-axis
    // [0, 1] * window-size -> screen-size
    return [normalizedX * this.width, normalizedY * this.height];
  }

  private screenToWorld(px: number, py: number): [number, number] {
    const { xMin, xMax, yMin, yMax } = this.viewport;
    // normalize
    const normalizedX = px / this.width;
    const normalizedY = py / this.height;
    // length on the screen (px)
    const lengthX = xMax - xMin;
    const lengthY = yMax - yMin;
    return [
      xMin + normalizedX * lengthX,
      // origin position upper left. so, it should be yMax - real-y-bias
      yMax - normalizedY * lengthY,
    ];
  }

  // --- render ---

  private draw(): void {
    this.clear();
    this.drawGrid();
    this.drawAxes();
    this.drawTicks();
    this.drawCurve();
  }

  private clear(): void {
    this.ctx.clearRect(0, 0, this.width, this.height);
  }

  private drawGrid(): void {
    const { xMin, xMax, yMin, yMax } = this.viewport;
    const xStep = this.getTickStep(xMax - xMin);
    const yStep = this.getTickStep(yMax - yMin);
    const color = getComputedStyle(this.canvas).color || "#888";

    this.ctx.save();
    this.ctx.beginPath();
    this.ctx.strokeStyle = color;
    this.ctx.globalAlpha = 0.15;
    this.ctx.lineWidth = 1;

    this.forEachTick(xMin, xMax, xStep, (x) => {
      const [px] = this.worldToScreen(x, 0);
      this.ctx.moveTo(px, 0);
      this.ctx.lineTo(px, this.height);
    });

    this.forEachTick(yMin, yMax, yStep, (y) => {
      const [, py] = this.worldToScreen(0, y);
      this.ctx.moveTo(0, py);
      this.ctx.lineTo(this.width, py);
    });

    this.ctx.stroke();
    this.ctx.restore();
  }

  private drawAxes(): void {
    const { xMin, xMax, yMin, yMax } = this.viewport;
    const color = getComputedStyle(this.canvas).color || "#888";

    this.ctx.save();
    this.ctx.beginPath();
    this.ctx.strokeStyle = color;
    this.ctx.globalAlpha = 0.75;
    this.ctx.lineWidth = 1.5;

    // if in viewport
    if (yMin <= 0 && yMax >= 0) {
      const [, py] = this.worldToScreen(0, 0);
      this.ctx.moveTo(0, py);
      this.ctx.lineTo(this.width, py);
    }

    if (xMin <= 0 && xMax >= 0) {
      const [px] = this.worldToScreen(0, 0);
      this.ctx.moveTo(px, 0);
      this.ctx.lineTo(px, this.height);
    }

    this.ctx.stroke();
    this.ctx.restore();
  }

  private drawTicks(): void {
    const { xMin, xMax, yMin, yMax } = this.viewport;
    const xStep = this.getTickStep(xMax - xMin);
    const yStep = this.getTickStep(yMax - yMin);
    const [originX, originY] = this.worldToScreen(0, 0);
    const axisX = Math.max(0, Math.min(this.width, originX));
    const axisY = Math.max(0, Math.min(this.height, originY));
    const color = getComputedStyle(this.canvas).color || "#888";

    this.ctx.save();
    this.ctx.fillStyle = color;
    this.ctx.strokeStyle = color;
    this.ctx.globalAlpha = 0.75;
    this.ctx.font = "12px sans-serif";
    this.ctx.lineWidth = 1;

    const labelAbove = axisY > this.height - 22;
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = labelAbove ? "bottom" : "top";
    this.forEachTick(xMin, xMax, xStep, (x) => {
      const [px] = this.worldToScreen(x, 0);

      this.ctx.beginPath();
      this.ctx.moveTo(px, axisY - 3);
      this.ctx.lineTo(px, axisY + 3);
      this.ctx.stroke();

      this.ctx.fillText(this.formatTick(x, xStep), px, axisY + (labelAbove ? -5 : 5));
    });

    const labelLeft = axisX > this.width - 50;
    this.ctx.textAlign = labelLeft ? "right" : "left";
    this.ctx.textBaseline = "middle";
    this.forEachTick(yMin, yMax, yStep, (y) => {
      // zero
      if (Math.abs(y) < yStep * 1e-8) {
        return;
      }

      const [, py] = this.worldToScreen(0, y);

      this.ctx.beginPath();
      this.ctx.moveTo(axisX - 3, py);
      this.ctx.lineTo(axisX + 3, py);
      this.ctx.stroke();

      this.ctx.fillText(this.formatTick(y, yStep), axisX + (labelLeft ? -5 : 5), py);
    });

    this.ctx.restore();
  }

  private drawCurve(): void {
    const { yMin, yMax } = this.viewport;
    const visibleYRange = yMax - yMin;
    const styles = getComputedStyle(this.canvas);
    const curveColor = styles.getPropertyValue("--chart-curve-color").trim() || "#3b82f6";

    // clip, not render point out of the bounder
    this.ctx.save();
    this.ctx.beginPath();
    this.ctx.rect(0, 0, this.width, this.height);
    this.ctx.clip();

    this.ctx.beginPath();
    this.ctx.strokeStyle = curveColor;
    this.ctx.lineWidth = 2;
    // need a curve
    this.ctx.lineJoin = "round";
    this.ctx.lineCap = "round";

    let pathStarted = false;
    let previousY: number | null = null;
    for (const [x, y] of this.data) {
      if (y === null || !Number.isFinite(x) || !Number.isFinite(y)) {
        pathStarted = false;
        previousY = null;
        continue;
      }

      const [px, py] = this.worldToScreen(x, y);
      if (!Number.isFinite(px) || !Number.isFinite(py)) {
        pathStarted = false;
        previousY = null;
        continue;
      }

      // it may be asymptotes, if gap is quite large do not connect item. e.g. tan(x)
      const discontinuous = previousY !== null && Math.abs(y - previousY) > visibleYRange * 2;
      if (!pathStarted || discontinuous) {
        // lift pen, do not connect item
        this.ctx.moveTo(px, py);
        pathStarted = true;
      } else {
        this.ctx.lineTo(px, py);
      }

      previousY = y;
    }

    this.ctx.stroke();
    this.ctx.restore();
  }

  // avoid unnecessary draw
  private requestDraw(): void {
    if (this.animationFrame !== null) {
      return;
    }

    this.animationFrame = requestAnimationFrame(() => {
      this.animationFrame = null;
      this.draw();
    });
  }

  // --- handler ---

  private handlePointerMove(event: PointerEvent): void {
    if (!this.dragging) {
      const rect = this.canvas.getBoundingClientRect();
      const pointerX = ((event.clientX - rect.left) / rect.width) * this.width;
      const pointerY = ((event.clientY - rect.top) / rect.height) * this.height;
      this.onTooltipChange?.(this.findNearestPoint(pointerX, pointerY));
      return;
    }

    this.onTooltipChange?.(null);

    // bias on screen
    const dx = event.clientX - this.lastPointerX;
    const dy = event.clientY - this.lastPointerY;
    const viewport = this.viewport;

    // bias in real world
    const worldDx = (dx / this.width) * (viewport.xMax - viewport.xMin);
    const worldDy = (dy / this.height) * (viewport.yMax - viewport.yMin);

    // update
    this.viewport.xMin = viewport.xMin - worldDx;
    this.viewport.xMax = viewport.xMax - worldDx;
    this.viewport.yMin = viewport.yMin + worldDy;
    this.viewport.yMax = viewport.yMax + worldDy;
    this.lastPointerX = event.clientX;
    this.lastPointerY = event.clientY;

    this.requestDraw();
    this.onViewportChange?.(this.viewport);
  }

  private handlePointerDown(event: PointerEvent): void {
    this.dragging = true;
    this.lastPointerX = event.clientX;
    this.lastPointerY = event.clientY;
    // continue when dragging out
    this.canvas.setPointerCapture(event.pointerId);
  }

  private handlePointerUp(_event: PointerEvent): void {
    this.dragging = false;
  }

  private handlePointerLeave(_event: PointerEvent): void {
    this.onTooltipChange?.(null);
  }

  private handleWheel(event: WheelEvent): void {
    event.preventDefault();

    // clean tooltip
    this.onTooltipChange?.(null);

    const rect = this.canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const [anchorX, anchorY] = this.screenToWorld(px, py);

    const factor = Math.exp(event.deltaY * 0.001);
    const viewport = this.viewport;

    this.viewport.xMin = anchorX + (viewport.xMin - anchorX) * factor;
    this.viewport.xMax = anchorX + (viewport.xMax - anchorX) * factor;
    this.viewport.yMin = anchorY + (viewport.yMin - anchorY) * factor;
    this.viewport.yMax = anchorY + (viewport.yMax - anchorY) * factor;

    this.requestDraw();
    this.onViewportChange?.(this.viewport);
  }

  private onResize(width: number, height: number): void {
    // high DPI adapt
    const dpr = window.devicePixelRatio || 1;

    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    this.width = width;
    this.height = height;
    this.requestDraw();
  }

  // --- utils ---

  private getTickStep(range: number, targetCount: number = 10): number {
    const roughStep = range / targetCount;
    const magnitude = 10 ** Math.floor(Math.log10(roughStep));
    const normalized = roughStep / magnitude;

    // 1, 2, 5, 10, 10^N...
    const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return factor * magnitude;
  }

  private forEachTick(
    min: number,
    max: number,
    step: number,
    callback: (value: number) => void,
  ): void {
    const first = Math.ceil(min / step);
    const last = Math.floor(max / step);
    for (let index = first; index <= last; index += 1) {
      callback(index * step);
    }
  }

  private formatTick(value: number, step: number): string {
    if (Math.abs(value) < step * 1e-8) {
      return "0";
    }

    if (Math.abs(value) >= 1e6 || Math.abs(value) < 1e-4) {
      return value.toExponential(2);
    }

    const decimals = Math.max(0, -Math.floor(Math.log10(step)));
    return Number(value.toFixed(Math.min(decimals, 12))).toString();
  }

  private findNearestPoint(pointerX: number, pointerY: number): TooltipPoint | null {
    if (this.data.length === 0) {
      return null;
    }

    const [worldX] = this.screenToWorld(pointerX, pointerY);

    // point is sorted with x-asix. satisfy binary search condition
    let low = 0;
    let high = this.data.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (this.data[middle][0] < worldX) {
        low = middle + 1;
      } else {
        high = middle;
      }
    }

    let nearest: TooltipPoint | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (
      let index = Math.max(0, low - 3);
      index < Math.min(this.data.length, low + 4);
      index += 1
    ) {
      const [x, y] = this.data[index];
      if (y === null) {
        continue;
      }

      const [canvasX, canvasY] = this.worldToScreen(x, y);
      const distance = Math.hypot(canvasX - pointerX, canvasY - pointerY);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = { x, y, canvasX, canvasY };
      }
    }

    // if cursor & curve distance less 12px display tooltip
    return nearestDistance <= 12 ? nearest : null;
  }
}
