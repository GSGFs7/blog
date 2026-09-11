import { createEffect, createMemo, createSignal, onCleanup, onMount, Show } from "solid-js";
import { render } from "solid-js/web";

import type { IslandElement } from "../../core/bootstrap";
import { formatTime } from "./format";
import { player } from "./player";
import type { MusicMetadata } from "./types";

import "./music.css";

const PAUSE_CLOSE_DELAY = 3_000;
const DOCK_EXIT_DURATION = 180;

interface DockState {
  track: MusicMetadata;
  time: number;
  duration: number;
}

let dockRoot: IslandElement | undefined;

export function ensureMusicDock() {
  if (dockRoot?.isConnected && dockRoot.__solidDispose__) {
    return;
  }

  const root: IslandElement = document.createElement("div");
  root.dataset.solidIsland = "MusicDock";
  document.body.append(root);
  const dispose = render(() => <MusicDock />, root);
  root.__solidDispose__ = () => {
    dispose();
    root.remove();
    dockRoot = undefined;
  };
  dockRoot = root;
}

export default function MusicDock() {
  let audio!: HTMLAudioElement;
  const activeSrc = createMemo(() => player.track()?.src);
  const [dock, setDock] = createSignal<DockState | null>(null);

  onMount(() => {
    onCleanup(player.attach(audio));
  });

  createEffect(() => {
    if (!activeSrc() || player.playing()) {
      return;
    }

    const timer = setTimeout(player.clear, PAUSE_CLOSE_DELAY);
    onCleanup(() => clearTimeout(timer));
  });

  createEffect(() => {
    const track = player.track();
    if (track) {
      setDock({ track, time: player.time(), duration: player.duration() });
      return;
    }
    if (!dock()) {
      return;
    }

    const timer = setTimeout(() => setDock(null), DOCK_EXIT_DURATION);
    onCleanup(() => clearTimeout(timer));
  });

  return (
    <>
      <audio ref={(element) => (audio = element)} preload="none" crossorigin="anonymous" />
      <Show when={dock()}>
        {(state) => (
          <section
            class="music-dock"
            aria-label="music player"
            data-state={player.track() ? "open" : "closed"}
            style={{ "background-color": state().track.background ?? "#29272e" }}
          >
            <div class="music-dock-control">
              <Show when={state().track.coverUrl}>
                {(cover) => <img class="music-dock-art" src={cover()} alt="" />}
              </Show>
              <button
                type="button"
                onClick={player.toggle}
                aria-busy={player.loading()}
                aria-label={player.playing() ? "pause" : "play"}
              >
                {player.loading() ? (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    class="lucide lucide-rotate-cw music-spin"
                  >
                    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                    <path d="M21 3v5h-5" />
                  </svg>
                ) : player.playing() ? (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    class="lucide lucide-pause"
                  >
                    <rect x="14" y="3" width="5" height="18" rx="1" />
                    <rect x="5" y="3" width="5" height="18" rx="1" />
                  </svg>
                ) : (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    class="lucide lucide-play"
                  >
                    <path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z" />
                  </svg>
                )}
              </button>
            </div>
            <div class="music-dock-info">
              <input
                type="range"
                aria-label="progress"
                aria-valuetext={`${formatTime(state().time)} of ${formatTime(state().duration)}`}
                min="0"
                max={state().duration || 0}
                step="0.1"
                value={state().time}
                disabled={!state().duration}
                onInput={(event) => player.seek(event.currentTarget.valueAsNumber)}
              />
              <div class="music-times">
                <span>{formatTime(state().time)}</span>
                <span>{formatTime(state().duration)}</span>
              </div>
            </div>
          </section>
        )}
      </Show>
    </>
  );
}
