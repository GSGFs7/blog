const PRESERVE_SELECTOR = "[data-app-preserve]";

interface PreservedPair {
  readonly current: HTMLElement;
  readonly incoming: HTMLElement;
}

export interface PreservationPlan {
  readonly pairs: readonly PreservedPair[];
  readonly roots: readonly HTMLElement[];
}

// collect preservation marks
function collect(root: HTMLElement): Map<string, HTMLElement> {
  const elements = Array.from(root.querySelectorAll<HTMLElement>(PRESERVE_SELECTOR));
  const byId = new Map<string, HTMLElement>();
  for (const element of elements) {
    if (!element.id || byId.has(element.id)) {
      throw new Error("Preserved nodes require unique, non-empty IDs");
    }
    if (element.parentElement?.closest(PRESERVE_SELECTOR)) {
      throw new Error("Nested preserved nodes are not supported");
    }

    const matches = root.querySelectorAll(`[id="${CSS.escape(element.id)}"]`);
    if (matches.length !== 1) {
      throw new Error(`Duplicate preserved node ID: ${element.id}`);
    }

    byId.set(element.id, element);
  }
  return byId;
}

export function preparePreservation(
  currentRoot: HTMLElement,
  incomingRoot: HTMLElement,
): PreservationPlan {
  const current = collect(currentRoot);
  const incoming = collect(incomingRoot);
  const pairs: PreservedPair[] = [];
  for (const [id, next] of incoming) {
    const previous = current.get(id);
    if (
      !previous ||
      previous.localName !== next.localName ||
      previous.namespaceURI !== next.namespaceURI ||
      previous.dataset.solidIsland !== next.dataset.solidIsland
    ) {
      continue;
    }

    pairs.push({ current: previous, incoming: next });
  }
  return {
    pairs,
    roots: pairs.map(({ current }) => current),
  };
}

export function isPreserved(node: Element, roots: readonly HTMLElement[]): boolean {
  return roots.some((root) => root === node || root.contains(node));
}
