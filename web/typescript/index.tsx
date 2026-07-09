// Do not import theme.ts here. it should be load in very early.

import "./core/htmx";
import { setupBehaviors } from "./core/behaviors";
import { setupLazyIsland } from "./core/lazy-islands";

setupBehaviors();
setupLazyIsland();
