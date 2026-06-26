import { createSignal } from "solid-js";

export function Counter({ initial }: Readonly<{ initial?: number }>) {
  const [count, setCount] = createSignal(Number.isNaN(Number(initial)) ? 0 : Number(initial));

  return (
    <div>
      <span>Count: {count()}</span>
      <button
        type="button"
        class="m-2 rounded-md border border-white/30 bg-gray-500/30 px-2 text-white"
        onClick={() => setCount((prev) => prev + 1)}
      >
        +1
      </button>
    </div>
  );
}
