const HEAD_START_SELECTOR = 'meta[name="app-dynamic-head-start"]';
const HEAD_END_SELECTOR = 'meta[name="app-dynamic-head-end"]';

export interface DynamicHeadRange {
  readonly start: HTMLMetaElement;
  readonly end: HTMLMetaElement;
  readonly nodes: Node[];
}

export function readDynamicHead(document: Document): DynamicHeadRange | null {
  const starts = document.head.querySelectorAll<HTMLMetaElement>(HEAD_START_SELECTOR);
  const ends = document.head.querySelectorAll<HTMLMetaElement>(HEAD_END_SELECTOR);
  // reject not standard structure
  if (starts.length !== 1 || ends.length !== 1) {
    return null;
  }

  const start = starts[0];
  const end = ends[0];
  if (start.parentNode !== document.head || end.parentNode !== document.head) {
    return null;
  }

  // it must can be parsed
  let current: Node | null = start.nextSibling;
  const nodes: Node[] = [];
  while (current && current !== end) {
    nodes.push(current);
    current = current.nextSibling;
  }
  if (current !== end || nodes.length === 0) {
    return null;
  }

  return {
    start,
    end,
    nodes,
  };
}

export function hasValidPageHead(document: Document): boolean {
  return (
    document.body.matches("body.site-body") &&
    document.head.querySelectorAll("title").length === 1 &&
    readDynamicHead(document) !== null
  );
}
