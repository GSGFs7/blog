import { setupIslands } from "../core/bootstrap";
import { COMPONENTS } from "../islands";

setupIslands(COMPONENTS);

(async function adminMount() {
  const textareaForMarkdownEditor = document.querySelector(
    '.solid-markdown-editor[data-editor-target="content"]',
  ) as HTMLTextAreaElement;
  // TODO: add a switch?
  if (textareaForMarkdownEditor) {
    const { render } = await import("solid-js/web");
    const { AdminPostEditor } = await import("./post_editor");

    // 1. create new element for render editor
    const newDiv = document.createElement("div");
    textareaForMarkdownEditor.before(newDiv);

    // 2. hidden textarea
    textareaForMarkdownEditor.style.display = "none";

    // 3. mount editor
    render(() => AdminPostEditor({ textarea: textareaForMarkdownEditor }), newDiv);
  }
})();
