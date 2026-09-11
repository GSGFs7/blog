import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import { cleanup as cleanupIslands } from "../../core/bootstrap";
import { coverBackground, extractMusicMetadata } from "./metadata";
import MusicDock from "./MusicDock.island";
import MusicTrack from "./MusicTrack.island";
import { player } from "./player";
import type { MusicMetadata } from "./types";

vi.mock("./metadata", () => ({
  extractMusicMetadata: vi.fn(async () => {
    throw new Error("CORS");
  }),
  coverBackground: vi.fn(),
}));
afterEach(() => {
  cleanup();
  cleanupIslands(document);
  vi.restoreAllMocks();
  vi.useRealTimers();
});

test("the dock mounts on first play, is reused, and can remount after navigation cleanup", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const play = vi
    .spyOn(HTMLMediaElement.prototype, "play")
    .mockImplementation(async function (this: HTMLAudioElement) {
      this.dispatchEvent(new Event("playing"));
    });
  render(() => <MusicTrack src="https://example.com/song.mp3" />);
  expect(document.querySelector("audio")).toBeNull();
  expect(document.querySelector('[data-solid-island="MusicDock"]')).toBeNull();
  await waitFor(() => expect(screen.getByRole("button", { name: "play song.mp3" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "play song.mp3" }));
  expect(play).toHaveBeenCalledOnce();
  expect(screen.getByRole("region", { name: "music player" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "pause song.mp3" })).toBeInTheDocument();
  const audio = document.querySelector("audio")!;
  fireEvent.click(screen.getByRole("button", { name: "pause song.mp3" }));
  expect(document.querySelectorAll("audio")).toHaveLength(1);
  expect(document.querySelector("audio")).toBe(audio);
  play.mockClear();
  cleanupIslands(document.body);
  expect(player.track()).toBeNull();
  expect(audio.hasAttribute("src")).toBe(false);
  expect(document.querySelector('[data-solid-island="MusicDock"]')).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "play song.mp3" }));
  expect(play).toHaveBeenCalledOnce();
  expect(document.querySelectorAll("audio")).toHaveLength(1);
});

test("cover color updates do not reload the image and repeated load events are bounded", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static revokeObjectURL = vi.fn();
    },
  );
  vi.mocked(extractMusicMetadata).mockResolvedValueOnce({
    src: "https://example.com/song.mp3",
    coverUrl: "blob:cover",
    title: "Song",
  });
  vi.mocked(coverBackground).mockReturnValue("rgb(30, 40, 50)");
  const { container, unmount } = render(() => <MusicTrack src="https://example.com/song.mp3" />);
  await waitFor(() => expect(container.querySelector("img")).not.toBeNull());
  const img = container.querySelector("img")!;
  const observer = new MutationObserver(() => {});
  observer.observe(img, { attributes: true, attributeFilter: ["src"] });
  try {
    fireEvent.load(img);
    expect(observer.takeRecords()).toHaveLength(0);
    fireEvent.load(img);
    expect(coverBackground).toHaveBeenCalledTimes(1);
    expect(container.querySelector("img")).toBe(img);
    expect(container.querySelector(".music-track")).toHaveStyle({
      backgroundColor: "rgb(30, 40, 50)",
    });
  } finally {
    observer.disconnect();
    unmount();
    vi.unstubAllGlobals();
  }
});

test("the loading placeholder never shares the cover slot with the play icon", async () => {
  let settle!: (value: MusicMetadata) => void;
  vi.mocked(extractMusicMetadata).mockImplementationOnce(
    () => new Promise<MusicMetadata>((resolve) => (settle = resolve)),
  );
  const { container } = render(() => <MusicTrack src="https://example.com/song.mp3" />);
  expect(container.querySelector(".music-note")).not.toBeNull();
  expect(container.querySelector(".music-play-icon")).toBeNull();
  settle({ src: "https://example.com/song.mp3", coverUrl: "blob:cover" });
  await waitFor(() => expect(container.querySelector("img")).not.toBeNull());
  expect(container.querySelector(".music-note")).toBeNull();
  expect(container.querySelector(".music-play-icon")).not.toBeNull();
});

test("a pause longer than three seconds closes the player", async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
  render(() => <MusicDock />);
  player.play({ src: "https://example.com/song.mp3" });
  expect(player.track()).not.toBeNull();
  await vi.advanceTimersByTimeAsync(2_000);
  expect(player.track()).not.toBeNull();
  await vi.advanceTimersByTimeAsync(1_000);
  expect(player.track()).toBeNull();
});

test("resuming within three seconds keeps the player open", async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
  render(() => <MusicDock />);
  player.play({ src: "https://example.com/song.mp3" });
  await vi.advanceTimersByTimeAsync(2_000);
  document.querySelector("audio")!.dispatchEvent(new Event("playing"));
  await vi.advanceTimersByTimeAsync(20_000);
  expect(player.track()).not.toBeNull();
});

test("the dock animates out before it unmounts", async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
  render(() => <MusicDock />);
  player.play({ src: "https://example.com/song.mp3", duration: 300 });
  const dock = document.querySelector(".music-dock")!;
  expect(dock).not.toBeNull();
  const audio = document.querySelector("audio")!;
  audio.currentTime = 42;
  audio.dispatchEvent(new Event("timeupdate"));
  expect(screen.getByText("0:42")).toBeInTheDocument();
  player.clear();
  expect(document.querySelector(".music-dock")).toBe(dock);
  expect(dock).toHaveAttribute("data-state", "closed");
  expect(screen.getByText("0:42")).toBeInTheDocument();
  expect(screen.getByText("5:00")).toBeInTheDocument();
  await vi.advanceTimersByTimeAsync(200);
  expect(document.querySelector(".music-dock")).toBeNull();
});

test("an unmounted active card hands its cover over to the player", async () => {
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.mocked(extractMusicMetadata).mockResolvedValueOnce({
    src: "https://example.com/song.mp3",
    coverUrl: "blob:cover",
  });
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
  render(() => <MusicDock />);
  const card = render(() => <MusicTrack src="https://example.com/song.mp3" />);
  await waitFor(() => expect(screen.getByRole("button", { name: "play song.mp3" })).toBeEnabled());
  player.play({ src: "https://example.com/song.mp3", coverUrl: "blob:cover" });
  expect(player.track()?.coverUrl).toBe("blob:cover");
  card.unmount();
  expect(revoke).not.toHaveBeenCalledWith("blob:cover");
  player.clear();
  expect(revoke).toHaveBeenCalledWith("blob:cover");
});

test("an unmounted inactive card revokes its own cover", async () => {
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.mocked(extractMusicMetadata).mockResolvedValueOnce({
    src: "https://example.com/other.mp3",
    coverUrl: "blob:other",
  });
  const card = render(() => <MusicTrack src="https://example.com/other.mp3" />);
  await waitFor(() => expect(screen.getByRole("button", { name: "play other.mp3" })).toBeEnabled());
  card.unmount();
  expect(revoke).toHaveBeenCalledWith("blob:other");
});

test("the dock layers the cover art under the play button", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => {});
  render(() => <MusicDock />);
  player.play({ src: "https://example.com/song.mp3", coverUrl: "blob:cover", duration: 300 });
  const control = document.querySelector(".music-dock-control")!;
  const art = control.querySelector("img.music-dock-art");
  expect(art).toHaveAttribute("src", "blob:cover");
  expect(art).toHaveAttribute("alt", "");
  expect(control.firstElementChild).toBe(art);
  expect(control.querySelector("button")).not.toBeNull();
  expect(screen.getByRole("slider", { name: "progress" })).toHaveAttribute(
    "aria-valuetext",
    "0:00 of 5:00",
  );
});

test("the dock shows a buffering icon and keeps the pause action", async () => {
  let paused = true;
  render(() => <MusicDock />);
  const audio = document.querySelector("audio")!;
  Object.defineProperty(audio, "paused", { get: () => paused });
  vi.spyOn(audio, "load").mockImplementation(() => {});
  vi.spyOn(audio, "play").mockImplementation(async () => {
    paused = false;
    audio.dispatchEvent(new Event("playing"));
  });
  const pause = vi.spyOn(audio, "pause").mockImplementation(() => {
    paused = true;
    audio.dispatchEvent(new Event("pause"));
  });
  player.play({ src: "https://example.com/song.mp3", duration: 300 });
  expect(document.querySelector(".lucide-pause")).not.toBeNull();
  audio.dispatchEvent(new Event("waiting"));
  expect(document.querySelector(".lucide-rotate-cw")).not.toBeNull();
  const button = screen.getByRole("button", { name: "pause" });
  expect(button).toHaveAttribute("aria-busy", "true");
  pause.mockClear();
  fireEvent.click(button);
  expect(pause).toHaveBeenCalledOnce();
  expect(document.querySelector(".lucide-play")).not.toBeNull();
  expect(button).not.toHaveAttribute("aria-busy", "true");
});
