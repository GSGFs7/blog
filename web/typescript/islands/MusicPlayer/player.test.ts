import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { musicSource } from "./format";
import { player } from "./player";

let audio: HTMLAudioElement;
let dispose: () => void;
let paused: boolean;
beforeEach(() => {
  paused = true;
  audio = document.createElement("audio");
  Object.defineProperty(audio, "paused", { get: () => paused });
  vi.spyOn(audio, "play").mockImplementation(async () => {
    paused = false;
    audio.dispatchEvent(new Event("play"));
    audio.dispatchEvent(new Event("playing"));
  });
  vi.spyOn(audio, "pause").mockImplementation(() => {
    paused = true;
    audio.dispatchEvent(new Event("pause"));
  });
  vi.spyOn(audio, "load").mockImplementation(() => {});
  dispose = player.attach(audio);
});
afterEach(() => {
  dispose();
  vi.restoreAllMocks();
});

test("switches songs and pauses/resumes the same song without resetting progress", () => {
  const first = { src: "https://example.com/a.mp3" };
  player.play(first);
  expect(player.playing()).toBe(true);
  audio.currentTime = 12;
  player.play(first);
  expect(player.playing()).toBe(false);
  expect(audio.currentTime).toBe(12);
  player.play(first);
  expect(player.playing()).toBe(true);
  player.play({ src: "https://example.com/b.mp3" });
  expect(audio.src).toBe("https://example.com/b.mp3");
  expect(player.time()).toBe(0);
});

test("metadata from inactive cards cannot change the active cover color", () => {
  player.play({ src: "https://example.com/a.mp3", background: "red" });
  player.update({ src: "https://example.com/b.mp3", background: "blue" });
  expect(player.track()?.background).toBe("red");
});

test("disposal releases the audio and ignores a stale rejected play promise", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(audio.play).mockImplementation(
    () =>
      new Promise((_, failure) => {
        reject = failure;
      }),
  );
  player.play({ src: "https://example.com/a.mp3" });
  dispose();
  reject(new Error("late failure"));
  await Promise.resolve();
  expect(audio.hasAttribute("src")).toBe(false);
  expect(player.track()).toBeNull();
  expect(player.error()).toBe("");
  expect(player.loading()).toBe(false);
});

test("reports playback failure and resets when the song ends", async () => {
  vi.mocked(audio.play).mockRejectedValue(new Error("blocked"));
  player.play({ src: "https://example.com/a.mp3" });
  await Promise.resolve();
  expect(player.error()).not.toBe("");
  audio.dispatchEvent(new Event("ended"));
  expect(player.track()).toBeNull();
});

test("accepts HTTP sources and rejects active or empty URLs", () => {
  expect(musicSource("/song.mp3")).toContain("/song.mp3");
  for (const src of ["javascript:alert(1)", "data:text/html,test", "", undefined]) {
    expect(musicSource(src)).toBeUndefined();
  }
});
