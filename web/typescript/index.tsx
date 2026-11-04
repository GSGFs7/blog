// Do not import theme.ts here. it should be load in very early.

import { setupBehaviors } from "./core/behaviors";
import { setupLazyIsland } from "./core/lazy-islands";
import { setupNavigation } from "./core/navigation/setup"; // import from sub-dir avoid share dependencies with other chunk

setupBehaviors();
await setupNavigation();
setupLazyIsland();
