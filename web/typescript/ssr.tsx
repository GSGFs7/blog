// compile this file with ssr mode.

import { NoHydration, renderToString } from "solid-js/web";

import { SSR_COMPONENTS, STATIC_COMPONENTS } from "./islands/ssr_registry";

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
    staticIslands: Object.fromEntries(
      Object.entries(STATIC_COMPONENTS).map(([name, Component]) => [
        name,
        renderToString(() => (
          // some component may be handled incorrectly by sanitize.
          // for this reaseon, disable hydration for itey.
          <NoHydration>
            <Component />
          </NoHydration>
        )),
      ]),
    ),
  };
}

export { generateHydrationScript } from "solid-js/web";
