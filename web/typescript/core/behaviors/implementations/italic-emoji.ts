import { queryAllIncludingRoot } from "../dom";
import type { Behavior } from "../types";

const selector = ".markdown-body em, .markdown-body i";

const emojiPattern =
  /\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?\p{Emoji_Modifier}?(?:\u200D\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?\p{Emoji_Modifier}?)*/gu;

function wrapTextNode(node: Text, document: Document): void {
  const matches = [...node.data.matchAll(emojiPattern)];
  if (matches.length === 0) {
    return;
  }

  const fragment = document.createDocumentFragment();
  let cursor = 0;
  for (const match of matches) {
    const index = match.index ?? 0;
    if (index > cursor) {
      fragment.append(node.data.slice(cursor, index));
    }

    const span = document.createElement("span");
    span.className = "md-emoji";
    span.textContent = match[0];
    fragment.append(span);
    cursor = index + match[0].length;
  }

  if (cursor < node.data.length) {
    fragment.append(node.data.slice(cursor));
  }
  node.replaceWith(fragment);
}

function wrapItalicEmoji(element: Element, document: Document): void {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];

  let current = walker.nextNode();
  while (current) {
    const parent = current.parentElement;
    if (!parent || !parent.closest(".md-emoji")) {
      textNodes.push(current as Text);
    }
    current = walker.nextNode();
  }
  for (const node of textNodes) {
    wrapTextNode(node, document);
  }
}

export function createItalicEmojiBehavior(): Behavior {
  return {
    mount(root, context) {
      for (const element of queryAllIncludingRoot<HTMLElement>(root, selector)) {
        wrapItalicEmoji(element, context.document);
      }
    },
  };
}
