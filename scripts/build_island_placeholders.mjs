#!/usr/bin/env node
// build solid static SSR placeholder HTML
// run `pnpm run build:ssr` first

import { writeFileSync } from "node:fs";

import { buildSsrManifest } from "../web/static/ssr/ssr.mjs";

writeFileSync(
    new URL("../web/static/ssr/solid-islands.json", import.meta.url),
    JSON.stringify(buildSsrManifest()),
);
