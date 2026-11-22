import { render } from "solid-js/web";

import { COMPONENTS } from "@/islands";

const { setupIslands } = await import("@/core/bootstrap");
setupIslands(COMPONENTS);

(async function adminMount() {
  const textareaForMarkdownEditor = document.querySelector(
    '.solid-markdown-editor[data-editor-target="content"]',
  ) as HTMLTextAreaElement;
  // TODO: add a switch?
  if (textareaForMarkdownEditor) {
    const { AdminPostEditor } = await import("./post_editor");

    // 1. create new element for render editor
    const newDiv = document.createElement("div");
    // avoid Django's flex rule cause page flashes at high speed
    newDiv.style.flex = "1 1 0";
    newDiv.style.minWidth = "0";
    textareaForMarkdownEditor.before(newDiv);

    // 2. hidden textarea
    textareaForMarkdownEditor.style.display = "none";

    // 3. mount editor
    render(() => AdminPostEditor({ textarea: textareaForMarkdownEditor }), newDiv);
  }
})();
