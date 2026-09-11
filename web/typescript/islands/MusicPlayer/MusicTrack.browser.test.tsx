import { cleanup, render } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import manifestJSON from "../../../static/ssr/solid-islands.json?raw";

import "../../styles/markdown.css";
import { extractMusicMetadata } from "./metadata";
import MusicTrack from "./MusicTrack.island";
import type { MusicMetadata } from "./types";

const placeholder: string = JSON.parse(manifestJSON).staticIslands.MusicTrack;

vi.mock("./metadata", () => ({
  extractMusicMetadata: vi.fn(),
  coverBackground: vi.fn(),
}));

afterEach(() => {
  cleanup();
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

test.each([320, 768])("music placeholder preserves layout at %i px", async (width) => {
  let settle!: (metadata: MusicMetadata) => void;
  vi.mocked(extractMusicMetadata).mockImplementationOnce(
    () => new Promise((resolve) => (settle = resolve)),
  );
  const article = document.createElement("article");
  article.className = "markdown-body";
  article.style.width = `${width}px`;
  article.innerHTML = `<span data-solid-island="MusicTrack">${placeholder}</span><p>Following text</p>`;
  document.body.append(article);
  const island = article.querySelector<HTMLElement>("[data-solid-island]")!;
  const following = article.querySelector("p")!;
  const initial = island.firstElementChild!.getBoundingClientRect();
  const followingTop = following.getBoundingClientRect().top;
  expect(initial.height).toBeGreaterThan(0);
  island.replaceChildren();
  render(() => <MusicTrack src="https://example.com/song.mp3" />, { container: island });

  const checkLayout = () => {
    const mounted = island.firstElementChild!.getBoundingClientRect();
    expect(mounted.height).toBe(initial.height);
    expect(mounted.width).toBe(initial.width);
    expect(following.getBoundingClientRect().top).toBe(followingTop);
    expect(document.querySelector("audio")).toBeNull();
  };
  checkLayout();
  settle({
    src: "https://example.com/song.mp3",
    title: "A long music title that should be truncated without shifting the following text",
    artist: "Artist",
    duration: 180,
    size: 5_242_880,
  });
  await vi.waitFor(() => expect(island.textContent).toContain("Artist"));
  checkLayout();
});
