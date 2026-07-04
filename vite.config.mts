import { resolve } from "node:path";

import tailwindcss from "@tailwindcss/vite";
import Sonda from "sonda/vite";
import type { Plugin } from "vite";
import solidPlugin from "vite-plugin-solid";
import { defineConfig } from "vitest/config";

// reload entre page when django template has updated
const djangoTemplateReload = (): Plugin => ({
  name: "django-template-reload",
  configureServer: (server) => {
    server.watcher.add([
      resolve(server.config.root, "web/templates"),
      resolve(server.config.root, "templates"),
    ]);
  },
  hotUpdate({ file, server, timestamp }) {
    if (this.environment.name !== "client" || !file.endsWith(".html")) {
      return;
    }

    // invalid TWCSS (hot update)
    const cssFile = resolve(server.config.root, "web/typescript/styles/globals.css");
    const modules = this.environment.moduleGraph.getModulesByFile(cssFile);
    const affectedModules = modules ? [...modules] : [];
    for (const module of affectedModules) {
      this.environment.moduleGraph.invalidateModule(module, undefined, timestamp, true);
    }

    this.environment.hot.send({
      type: "full-reload",
      path: "*",
    });

    return affectedModules;
  },
});

export default defineConfig(({ command, isSsrBuild }) => {
  let rolldownInputs: Record<string, string>;
  if (isSsrBuild) {
    rolldownInputs = {
      ssr: "web/typescript/ssr.tsx",
    };
  } else {
    rolldownInputs = {
      index: "web/typescript/index.tsx",
      loadTheme: "web/typescript/core/theme.ts",
      globalCss: "web/typescript/styles/globals.css",
      fontCss: "web/typescript/styles/font.css",
      markdownCss: "web/typescript/styles/markdown.css",
      // admin
      admin: "web/typescript/admin/index.ts",
    };
  }

  return {
    base: command === "build" ? "/static/dist/" : "/",
    plugins: [
      !isSsrBuild && tailwindcss(),
      solidPlugin({ ssr: isSsrBuild }),
      djangoTemplateReload(),
      !isSsrBuild &&
        process.env.ANALYZE === "1" &&
        Sonda({
          filename: "bundle-report",
          gzip: true,
          brotli: true,
          open: true,
        }),
    ],
    build: {
      outDir: isSsrBuild ? "web/static/ssr" : "web/static/dist",
      assetsDir: "",
      manifest: !isSsrBuild && "manifest.json",
      ssr: isSsrBuild,
      ssrEmitAssets: false,
      rolldownOptions: {
        input: rolldownInputs,
      },
      cssMinify: "lightningcss",
      cssCodeSplit: true,
      minify: "oxc",
      sourcemap: process.env.ANALYZE === "1",
    },
    ssr: {
      // put the dependencies to the bundle
      noExternal: true,
    },
    server: {
      port: 5173,
      strictPort: true,
      origin: "http://localhost:5173",
      headers: {
        "Cross-Origin-Resource-Policy": "cross-origin",
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./web/typescript/test/setup.ts"],
      coverage: {
        reporter: ["text", "json", "lcov"],
      },
    },
  };
});
