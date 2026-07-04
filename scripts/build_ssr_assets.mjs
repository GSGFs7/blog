#!/usr/bin/env node
// run `pnpm run build:ssr` first

import { writeFileSync } from "node:fs";

import { buildSsrManifest, generateHydrationScript } from "../web/static/ssr/ssr.mjs";

writeFileSync(
    new URL("../web/static/ssr/solid-islands.json", import.meta.url),
    JSON.stringify(buildSsrManifest()),
);

writeFileSync(
    new URL("../web/static/ssr/solid-hydrate-script.js", import.meta.url),
    // tailing include a '<!--xs-->' comment.
    // it's an anchor for `injectScripts()`.
    // it only used by server side string concatenation.
    // remove it.
    generateHydrationScript().replace(/^<script>([\s\S]*)<\/script>.*$/, "$1"),
);
