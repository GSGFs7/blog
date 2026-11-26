import { createSignal } from "solid-js";

import type { MusicMetadata } from "./types";

const [track, setTrack] = createSignal<MusicMetadata | null>(null);
const [playing, setPlaying] = createSignal(false);
const [loading, setLoading] = createSignal(false);
const [time, setTime] = createSignal(0);
const [duration, setDuration] = createSignal(0);
const [error, setError] = createSignal("");
let audio: HTMLAudioElement | undefined;
let release: (() => void) | undefined;
let attempt = 0;
let retainedCover: string | undefined;
// sync
let currentTrack: MusicMetadata | null = null;
let currentDuration = 0;

function writeTrack(next: MusicMetadata | null = null) {
  currentTrack = next;
  setTrack(next);
}

function writeDuration(next: number) {
  currentDuration = next;
  setDuration(next);
}

function releaseRetainedCover() {
  if (!retainedCover) {
    return;
  }

  URL.revokeObjectURL(retainedCover);
  retainedCover = undefined;
}

function clear() {
  attempt++;
  audio?.pause();
  audio?.removeAttribute("src");
  audio?.load();
  releaseRetainedCover();
  writeTrack(null);
  setPlaying(false);
  setLoading(false);
  setTime(0);
  writeDuration(0);
  setError("");
}

async function resume() {
  const current = audio;
  if (!current || !currentTrack) {
    return;
  }

  const token = ++attempt;
  setError("");
  setLoading(true);

  try {
    await current.play();
  } catch (reason) {
    if (token !== attempt || current !== audio) {
      return;
    }
    setLoading(false);

    if (!(reason instanceof DOMException && reason.name === "AbortError")) {
      setError("playing failed");
    }
  }
}

function toggle() {
  if (!audio || !currentTrack) {
    return;
  }

  if (audio.paused) {
    void resume();
  } else {
    attempt++;
    audio.pause();
  }
}

function play(next: MusicMetadata) {
  if (!audio) {
    return;
  }
  if (currentTrack?.src === next.src) {
    toggle();
    return;
  }

  clear();
  writeTrack(next);
  writeDuration(next.duration ?? 0);
  audio.src = next.src;
  void resume();
}

function attach(element: HTMLAudioElement) {
  release?.();
  audio = element;

  const controller = new AbortController();
  const listen = (name: string, handler: () => void) =>
    element.addEventListener(
      name,
      () => {
        if (currentTrack) {
          handler();
        }
      },
      { signal: controller.signal },
    );
  listen("playing", () => {
    setPlaying(true);
    setLoading(false);
  });
  listen("play", () => setPlaying(true));
  listen("pause", () => {
    setPlaying(false);
    setLoading(false);
  });
  listen("waiting", () => setLoading(true));
  listen("canplay", () => setLoading(false));
  listen("timeupdate", () => setTime(element.currentTime));
  listen("durationchange", () =>
    writeDuration(Number.isFinite(element.duration) ? element.duration : 0),
  );
  listen("ended", clear);
  listen("error", () => {
    setPlaying(false);
    setLoading(false);
    setError("loading failed");
  });

  const dispose = () => {
    controller.abort();
    clear();
    audio = undefined;
    release = undefined;
  };
  release = dispose;

  return () => {
    if (audio === element) {
      dispose();
    }
  };
}

export const player = {
  track,
  playing,
  loading,
  time,
  duration,
  error,
  attach,
  play,
  toggle,
  clear,
  retainCover(url: string) {
    retainedCover = url;
  },
  update(next: MusicMetadata) {
    if (currentTrack?.src === next.src) {
      if (retainedCover && retainedCover !== next.coverUrl) {
        releaseRetainedCover();
      }
      writeTrack(next);
    }
  },
  seek(value: number) {
    if (audio && Number.isFinite(value) && currentDuration > 0) {
      audio.currentTime = Math.max(0, Math.min(currentDuration, value));
      setTime(audio.currentTime);
    }
  },
};
