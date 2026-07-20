// NOTE: import this file only in ssr environment

import type { Component } from "solid-js";

import type { ComponentProps } from "../types";
import Counter from "./Counter";
import WIP from "./WIP";

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
  WIP: {
    component: WIP,
    placeholderProps: {
      title: "施工中",
      message: "正在努力创建新文件夹",
    },
  },
};
