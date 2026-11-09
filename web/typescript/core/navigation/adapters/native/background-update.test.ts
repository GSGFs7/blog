import { afterEach, beforeEach, expect, test } from "vitest";

import { canApplyBackgroundUpdate, setupBackgroundUpdateGuard } from "./background-update";

let guard: ReturnType<typeof setupBackgroundUpdateGuard>;

beforeEach(() => {
  document.body.innerHTML = "";
  guard = setupBackgroundUpdateGuard(document);
});

afterEach(() => guard.dispose());

test("allows an update when focus is on the document and no form is dirty", () => {
  document.body.innerHTML = "<main><p>content</p></main>";

  expect(canApplyBackgroundUpdate(document)).toBe(true);
});

test("blocks an update while any non-preserved element is focused", () => {
  document.body.innerHTML = '<a href="/about">About</a>';

  document.querySelector("a")!.focus();

  expect(canApplyBackgroundUpdate(document)).toBe(false);
});

test("allows an update while focus stays inside a preserved root", () => {
  document.body.innerHTML =
    '<div data-app-preserve><input value="player"></div><main>content</main>';

  document.querySelector("input")!.focus();

  expect(canApplyBackgroundUpdate(document)).toBe(true);
});

test.each([
  ['<input value="">', (element: HTMLElement) => ((element as HTMLInputElement).value = "edited")],
  [
    "<textarea></textarea>",
    (element: HTMLElement) => ((element as HTMLTextAreaElement).value = "edited"),
  ],
  [
    '<input type="checkbox">',
    (element: HTMLElement) => ((element as HTMLInputElement).checked = true),
  ],
  [
    "<select><option>one</option><option>two</option></select>",
    (element: HTMLElement) => ((element as HTMLSelectElement).selectedIndex = 1),
  ],
])("blocks an update when a form control is dirty: %s", (html, mutate) => {
  document.body.innerHTML = `<main>${html}</main>`;
  const control = document.querySelector<HTMLElement>("main > *")!;
  mutate(control);
  control.blur();

  expect(canApplyBackgroundUpdate(document)).toBe(false);
});

test("allows an update when the dirty control lives in a preserved root", () => {
  document.body.innerHTML = '<div data-app-preserve><input value=""></div><main>content</main>';
  const input = document.querySelector("input")!;
  input.value = "edited";
  input.blur();

  expect(canApplyBackgroundUpdate(document)).toBe(true);
});

test("does not treat the default form values as user input", () => {
  document.body.innerHTML = `
    <main>
      <input value="default">
      <textarea>default</textarea>
      <input type="checkbox" checked>
      <select><option selected>one</option><option>two</option></select>
    </main>
  `;

  expect(canApplyBackgroundUpdate(document)).toBe(true);
});

test.each([
  "<select><option>one</option><option>two</option></select>",
  "<select><option disabled>one</option><option>two</option></select>",
  "<select multiple><option>one</option><option>two</option></select>",
  "<select size='2'><option>one</option><option>two</option></select>",
  "<select><option selected>one</option><option selected>two</option></select>",
  "<select form='other' name='reset'><option>one</option><option>two</option></select>",
])("allows a pristine select with browser defaults: %s", (html) => {
  document.body.innerHTML = html;
  expect(guard.canApply()).toBe(true);

  const select = document.querySelector("select")!;
  const selected = Array.from(select.options, (option) => option.selected);
  expect(guard.canApply()).toBe(true);
  expect(Array.from(select.options, (option) => option.selected)).toEqual(selected);
});

test("allows updates after a select returns to its implicit default", () => {
  document.body.innerHTML = "<select><option>one</option><option>two</option></select>";
  const select = document.querySelector("select")!;
  select.selectedIndex = 1;
  expect(guard.canApply()).toBe(false);
  select.selectedIndex = 0;
  expect(guard.canApply()).toBe(true);
});

test("detects changes to a multi-select", () => {
  document.body.innerHTML =
    "<select multiple><option selected>one</option><option>two</option></select>";
  document.querySelector("select")!.options[1].selected = true;
  expect(guard.canApply()).toBe(false);
});

test.each(["true", "", "plaintext-only"])(
  "protects edited contenteditable=%s after focus leaves it",
  (mode) => {
    document.body.innerHTML = `<div contenteditable="${mode}" tabindex="0"><span>initial</span></div>`;
    const editor = document.querySelector<HTMLElement>("div")!;
    expect(guard.canApply()).toBe(true);
    editor.focus();
    const text = editor.querySelector("span")!;
    text.textContent = "unsaved edits";
    text.dispatchEvent(new InputEvent("input", { bubbles: true }));
    editor.blur();

    expect(guard.canApply()).toBe(false);
    editor.remove();
    expect(guard.canApply()).toBe(true);
  },
);

test("does not track input inside a non-editable descendant", () => {
  document.body.innerHTML =
    '<div contenteditable="true"><span contenteditable="false">fixed</span></div>';
  document.querySelector("span")!.dispatchEvent(new InputEvent("input", { bubbles: true }));
  expect(guard.canApply()).toBe(true);
});

test("ignores edited content inside preserved roots", () => {
  document.body.innerHTML =
    '<div data-app-preserve><div contenteditable="true">initial</div></div>';
  document
    .querySelector("[contenteditable]")!
    .dispatchEvent(new InputEvent("input", { bubbles: true }));
  expect(guard.canApply()).toBe(true);
});

test("lets components declare and clear dirty state", () => {
  document.body.innerHTML = '<div data-solid-island="Editor"></div>';
  const component = document.querySelector("div")!;
  component.setAttribute("data-nav-dirty", "");
  expect(guard.canApply()).toBe(false);
  component.removeAttribute("data-nav-dirty");
  expect(guard.canApply()).toBe(true);
});

test("ignores component dirty state in preserved roots", () => {
  document.body.innerHTML = "<div data-app-preserve><div data-nav-dirty></div></div>";
  expect(guard.canApply()).toBe(true);
});

test("teardown stops tracking input", () => {
  guard.dispose();
  document.body.innerHTML = '<div contenteditable="true">initial</div>';
  document.querySelector("div")!.dispatchEvent(new InputEvent("input", { bubbles: true }));
  expect(guard.canApply()).toBe(true);
});
