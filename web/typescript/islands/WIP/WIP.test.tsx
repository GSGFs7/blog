import { cleanup, render, screen } from "@solidjs/testing-library";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { WIP } from "./WIP.island";

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0.5);
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("renders default content", () => {
  render(() => <WIP />);

  expect(screen.getByText("施工中")).toBeInTheDocument();
  expect(screen.getByText("正在努力创建新文件夹")).toBeInTheDocument();
  expect(screen.getByText("当前进度: 🛠️ 构建环境")).toBeInTheDocument();
});

test("renders custom content", () => {
  render(() => <WIP title="Almost ready" message="Finishing the last task" />);

  expect(screen.getByText("Almost ready")).toBeInTheDocument();
  expect(screen.getByText("Finishing the last task")).toBeInTheDocument();
});

test("updates progress after the timer fires", () => {
  render(() => <WIP />);

  vi.advanceTimersByTime(400);

  expect(screen.getByText("当前进度: 📦 打包资源")).toBeInTheDocument();
  expect(document.querySelector<HTMLElement>(".h-2.animate-pulse")).toHaveStyle({
    width: "128px",
  });
});
