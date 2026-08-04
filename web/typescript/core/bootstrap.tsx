// similar to Astro.js, a jsx component is an JS island

import { render, hydrate } from "solid-js/web";

import type { ComponentProps, ComponentRegistry } from "../types";
import { APP_PAGE_EVENT, type PageSwapDetail } from "./navigation";

let registry: ComponentRegistry = {};

type IslandElement = HTMLElement & {
  __solidDispose__?: () => void;
  __solidMountToken__?: symbol; // avoid concurrency issues
};

function parseProps(componentName: string, propsJSON: string | null): ComponentProps {
  try {
    return JSON.parse(propsJSON ?? "{}") as ComponentProps;
  } catch (error) {
    console.error(`Failed to parse props for ${componentName}:`, error);
    return {};
  }
}

// mount solid component
async function mountIsland(element: IslandElement): Promise<void> {
  if (element.__solidDispose__ || element.__solidMountToken__) {
    // avoid duplicate mounting
    return;
  }

  // mark with a unique symbol
  const token = Symbol("island token");
  element.__solidMountToken__ = token;

  try {
    // get the component
    const componentName = element.dataset.solidIsland as string;
    const loadComponent = registry[componentName];
    if (!loadComponent) {
      console.warn(`Solid component '${componentName}' not found in registry.`);
      return;
    }

    const Component = await loadComponent();
    if (!element.isConnected || element.__solidMountToken__ !== token) {
      return;
    }

    // get component props
    const props = parseProps(componentName, element.dataset.props ?? "{}");

    // check 'data-solid-ssr' flag
    if (Object.hasOwn(element.dataset, "solidSsr")) {
      // about 'renderId':
      // now frontend arch is island, it like this:
      //  A -> hydrate(A, A container)
      //  B -> hydrate(B, B container)
      // no potential conflict, 'renderId' is useless now
      try {
        element.__solidDispose__ = hydrate(() => <Component {...props} />, element);
      } catch (error) {
        console.warn(
          `Failed to hydrate Solid island '${componentName}', falling back to CSR.`,
          error,
        );

        // fallback to CSR
        element.replaceChildren();
        element.__solidDispose__ = render(() => <Component {...props} />, element);
      }
    } else {
      element.replaceChildren();
      element.__solidDispose__ = render(() => <Component {...props} />, element);
    }
  } finally {
    if (element.__solidMountToken__ === token) {
      delete element.__solidMountToken__;
    }
  }
}

export function bootstrap(root: ParentNode = document) {
  root.querySelectorAll("[data-solid-island]").forEach((element) => {
    void mountIsland(element as IslandElement);
  });
}

export function cleanup(root: ParentNode) {
  root.querySelectorAll("[data-solid-island]").forEach((element) => {
    const island = element as IslandElement;
    island.__solidDispose__?.();
    delete island.__solidDispose__;
    delete island.__solidMountToken__;
  });
}

function handleBeforeSwap(event: CustomEvent<PageSwapDetail>) {
  cleanup(event.detail.root);
}

function handleAfterSwap(event: CustomEvent<PageSwapDetail>) {
  bootstrap(event.detail.root);
}

export function setupIslands(components: ComponentRegistry) {
  registry = components;

  // init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => bootstrap());
  } else {
    bootstrap();
  }

  document.addEventListener(APP_PAGE_EVENT.beforeSwap, handleBeforeSwap);
  document.addEventListener(APP_PAGE_EVENT.afterSwap, handleAfterSwap);
}
