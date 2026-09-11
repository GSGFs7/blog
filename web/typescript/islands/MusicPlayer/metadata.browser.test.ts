import { expect, test } from "vitest";

import { coverBackground } from "./metadata";

function solidCover(color: string) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 16;
  const context = canvas.getContext("2d")!;
  context.fillStyle = color;
  context.fillRect(0, 0, 16, 16);
  return canvas as unknown as HTMLImageElement;
}

function relativeLuminance(color: string) {
  const [r, g, b] = color.match(/\d+/g)!.map((value) => {
    const channel = Number(value) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

test("bright covers are darkened until white text reaches 7:1 contrast", () => {
  for (const cover of ["#ffffff", "#f2f2f2", "#fff200", "#00ffff"]) {
    const background = coverBackground(solidCover(cover));
    expect(background).toBeDefined();
    expect(relativeLuminance(background!)).toBeLessThanOrEqual(0.1);
  }
});

test("dark covers keep their sampled color", () => {
  expect(coverBackground(solidCover("#202020"))).toBe("rgb(14, 14, 14)");
});
