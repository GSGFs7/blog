// compile this file with ssr mode.

import { renderToString } from "solid-js/web";

import { SSR_COMPONENTS } from "./islands/ssr_registry";

type Props = Record<string, unknown>;

export function renderIsland(name: string, props: Props = {}) {
  const island = SSR_COMPONENTS[name];
  if (!island) {
    throw new Error(`Unknown SSR component: ${name}`);
  }

  const Component = island.component;
  return renderToString(() => <Component {...props} />);
}

export function buildSsrManifest() {
  const islands = Object.fromEntries(
    Object.entries(SSR_COMPONENTS).map(([name, island]) => {
      const props = island.placeholderProps ?? {};
      return [
        name,
        {
          props,
          html: renderIsland(name, props),
        },
      ];
    }),
  );

  return {
    islands,
  };
}

export { generateHydrationScript } from "solid-js/web";
