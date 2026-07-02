import type { Component as SolidComponent } from "solid-js";

export type ComponentProps = Record<string, unknown>;
export type ComponentRegistry = Record<string, () => Promise<SolidComponent<ComponentProps>>>;
