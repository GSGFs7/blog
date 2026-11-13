import { expect, test } from "vitest";

import markdownCss from "./markdown.css?raw";

const CONTAINER = ".markdown-body";
const ISLAND_GUARD = ":not(:where([data-solid-island] *)";

function extractSelectors(css: string): string[] {
  const source = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const selectors: string[] = [];
  let buffer = "";
  let quote: string | null = null;

  for (const char of source) {
    if (quote !== null) {
      buffer += char;
      if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      buffer += char;
      continue;
    }
    if (char === "{") {
      const selector = buffer.replace(/\s+/g, " ").trim();
      if (selector !== "" && !selector.startsWith("@")) selectors.push(selector);
      buffer = "";
      continue;
    }
    if (char === "}" || char === ";") {
      buffer = "";
      continue;
    }
    buffer += char;
  }

  return selectors;
}

function splitSelectorList(selector: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = "";

  for (const char of selector) {
    if (char === "(") depth += 1;
    if (char === ")") depth -= 1;
    if (char === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  parts.push(current.trim());

  return parts;
}

const descendantSelectors = extractSelectors(markdownCss)
  .flatMap(splitSelectorList)
  .filter((part) => {
    const index = part.indexOf(CONTAINER);
    if (index === -1) return false;
    return /[\s>+~]/.test(part.slice(index + CONTAINER.length));
  });

test("scans the Markdown stylesheet", () => {
  expect(descendantSelectors.length).toBeGreaterThan(50);
});

test("every Markdown descendant selector excludes island internals", () => {
  const unguarded = descendantSelectors.filter((part) => !part.includes(ISLAND_GUARD));

  expect(unguarded).toEqual([]);
});

test("the island guard precedes pseudo-elements", () => {
  const misordered = descendantSelectors.filter(
    (part) => part.includes("::") && part.indexOf(ISLAND_GUARD) > part.indexOf("::"),
  );

  expect(misordered).toEqual([]);
});
