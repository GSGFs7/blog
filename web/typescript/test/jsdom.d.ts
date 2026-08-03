declare module "jsdom" {
  export class JSDOM {
    constructor(html: string, options?: { runScripts?: "outside-only" | "dangerously" });
    readonly window: Window;
  }
}
