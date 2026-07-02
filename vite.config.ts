import tailwindcss from "@tailwindcss/vite";
import type { Plugin } from "vite";
import solidPlugin from "vite-plugin-solid";
import { defineConfig } from "vitest/config";

// reload entre page when django template has updated
const djangoTemplateReload = (): Plugin => ({
  name: "django-template-reload",
  configureServer: (server) => {
    const templateDirs = ["web/templates/", "templates/"];
    server.watcher.add(templateDirs);

    const reload = (path: string): void => {
      if (path.endsWith(".html")) {
        server.ws.send({ type: "full-reload" });
      }
    };
    server.watcher.on("add", reload);
    server.watcher.on("change", reload);
    server.watcher.on("unlink", reload);
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
      styles: "web/typescript/styles/globals.css",
      baseLayoutCss: "web/typescript/styles/base.css",
      navbarCss: "web/typescript/styles/navbar.css",
      footerCss: "web/typescript/styles/footer.css",
      fontCss: "web/typescript/styles/font.css",
      markdownCss: "web/typescript/styles/markdown.css",
      // admin
      admin: "web/typescript/admin/index.ts",
    };
  }

  return {
    base: command === "build" ? "/static/dist/" : "/",
    plugins: [!isSsrBuild && tailwindcss(), solidPlugin({ ssr: isSsrBuild }), djangoTemplateReload()],
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
