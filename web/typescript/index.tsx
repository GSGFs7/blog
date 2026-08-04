// Do not import theme.ts here. it should be load in very early.

import { setupBehaviors } from "./core/behaviors";
import { setupLazyIsland } from "./core/lazy-islands";
import { setupNavigation } from "./core/navigation";

await setupNavigation();
setupBehaviors();
setupLazyIsland();
