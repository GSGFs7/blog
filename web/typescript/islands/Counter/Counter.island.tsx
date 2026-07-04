import { createSignal, onMount } from "solid-js";

export function Counter(props: Readonly<{ initial?: unknown }>) {
  const [count, setCount] = createSignal(0);

  onMount(() => {
    const initial = Number(props.initial);
    setCount(Number.isNaN(initial) ? 0 : initial);
  });

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
