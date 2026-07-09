// NOTE: import this file only in ssr environment

import type { Component } from "solid-js";

import type { ComponentProps } from "../types";
import Counter from "./Counter";

type IslandDefinition = {
  component: Component<ComponentProps>;
  placeholderProps?: ComponentProps;
};

export const SSR_COMPONENTS: Record<string, IslandDefinition> = {
  Counter: {
    component: Counter,
    placeholderProps: {
      initial: 0,
    },
  },
};
