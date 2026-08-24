import type { Component as SolidComponent } from "solid-js";

import type { ComponentProps } from "../types";

// use dynamic import. avoid js size too large
export const COMPONENTS: Record<string, () => Promise<SolidComponent<ComponentProps>>> = {
  Counter: async () => (await import("./Counter")).default,
  PythonREPL: async () => (await import("./PythonREPL")).default,
  PythonPlayground: async () => (await import("./PythonREPL/PythonPlayground.island")).default,
  Chart: async () => (await import("./Chart")).default,
  WIP: async () => (await import("./WIP")).default,
  MusicTrack: async () => (await import("./MusicPlayer/MusicTrack.island")).default,
  MusicDock: async () => (await import("./MusicPlayer/MusicDock.island")).default,
} as const;
