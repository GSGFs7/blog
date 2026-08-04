import { behaviorRegistry } from "./registry";
import { startBehaviorRuntime } from "./runtime";

// weak ref. the fn's lifecycle follow Document
const activeSetups = new WeakMap<Document, () => void>();

// this makesure all behaviors init only once
export function setupBehaviors(document: Document = window.document): () => void {
  // call clean fn
  activeSetups.get(document)?.();

  let stopped = false;
  const stopRuntime = startBehaviorRuntime(document, behaviorRegistry);
  // tell caller how to clean this
  const teardown = () => {
    if (stopped) {
      return;
    }

    stopped = true;
    stopRuntime();
    if (activeSetups.get(document) === teardown) {
      activeSetups.delete(document);
    }
  };

  // registry this behavior
  activeSetups.set(document, teardown);
  return teardown;
}
