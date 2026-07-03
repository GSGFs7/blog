// Do not import theme.ts here. it should be load in very early.

import "./core/htmx";
import { setupBehaviors } from "./core/behaviors";
import { setupIslands } from "./core/bootstrap";
import { COMPONENTS } from "./islands";

setupBehaviors();
setupIslands(COMPONENTS);
