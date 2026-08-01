export * from "./events";
export { setupNavigation } from "./setup";

// DO NOT import "./htmx-adapter"
// it will import HTMX very early and make some side effects
