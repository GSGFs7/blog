const PRESERVED_SELECTOR = "[data-app-preserve]";

function isPreserved(element: Element): boolean {
  return element.closest(PRESERVED_SELECTOR) !== null;
}

function hasDirtySelect(select: HTMLSelectElement): boolean {
  const defaults = select.cloneNode(true) as HTMLSelectElement;
  defaults.removeAttribute("form");

  const form = select.ownerDocument.createElement("form");
  form.append(defaults);
  // ```html
  // <form>
  //   <select name="reset">...</select>
  // </form>
  // ```
  // it will cover the .reset method
  HTMLFormElement.prototype.reset.call(form);

  return Array.from(select.options).some(
    (option, index) => option.selected !== defaults.options[index].selected,
  );
}

function isDirtyFormControl(element: Element): boolean {
  if (isPreserved(element)) {
    return false;
  }

  if (element instanceof HTMLSelectElement) {
    return hasDirtySelect(element);
  }

  if (
    element instanceof HTMLInputElement &&
    (element.type === "checkbox" || element.type === "radio")
  ) {
    return element.checked !== element.defaultChecked;
  }

  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    return element.value !== element.defaultValue;
  }

  return false;
}

function hasDirtyFormControl(document: Document): boolean {
  return Array.from(document.querySelectorAll("input, textarea, select")).some(isDirtyFormControl);
}

export function canApplyBackgroundUpdate(document: Document): boolean {
  const active = document.activeElement;
  if (
    active instanceof Element &&
    active !== document.body &&
    active !== document.documentElement &&
    !isPreserved(active)
  ) {
    return false;
  }

  return (
    !Array.from(document.querySelectorAll("[data-nav-dirty]")).some(
      (element) => !isPreserved(element),
    ) && !hasDirtyFormControl(document)
  );
}

// revalidate only
export function setupBackgroundUpdateGuard(document: Document): {
  canApply(): boolean;
  dispose(): void;
} {
  const controller = new AbortController();
  const edited = new WeakSet<Element>();

  // contenteditable check
  document.addEventListener(
    "input",
    (event) => {
      const target = event.target;
      const editable = target instanceof Element ? target.closest("[contenteditable]") : null;
      const mode = editable?.getAttribute("contenteditable")?.toLowerCase();
      if (editable && (mode === "" || mode === "true" || mode === "plaintext-only")) {
        edited.add(editable);
      }
    },
    { capture: true, signal: controller.signal },
  );

  return {
    canApply: () =>
      canApplyBackgroundUpdate(document) &&
      !Array.from(document.querySelectorAll("[contenteditable]")).some(
        (element) => edited.has(element) && !isPreserved(element),
      ),
    dispose: () => controller.abort(),
  };
}
