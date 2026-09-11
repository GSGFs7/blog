import { createMemo, createSignal, onCleanup, onMount, Show } from "solid-js";

import { fileTitle, formatTime, musicSource } from "./format";
import { coverBackground, extractMusicMetadata } from "./metadata";
import { ensureMusicDock } from "./MusicDock.island";
import { player } from "./player";
import type { MusicMetadata } from "./types";

import "./music.css";

export default function MusicTrack(props: { src?: unknown }) {
  let sampledCover: string | undefined;
  const [metadata, setMetadata] = createSignal<MusicMetadata>({ src: "" });
  const [invalid, setInvalid] = createSignal(false);
  const coverUrl = createMemo(() => metadata().coverUrl);

  const active = () => player.track()?.src === metadata().src;
  const playing = () => active() && player.playing();
  const update = (next: MusicMetadata) => {
    setMetadata(next);
    player.update(next);
  };

  onMount(() => {
    const src = musicSource(props.src);
    if (!src) {
      setInvalid(true);
      return;
    }
    setMetadata({ src, title: fileTitle(src) });

    const controller = new AbortController();
    let cover: string | undefined;
    onCleanup(() => {
      controller.abort();
      if (!cover) {
        return;
      }
      if (player.track()?.coverUrl === cover) {
        player.retainCover(cover);
        return;
      }
      URL.revokeObjectURL(cover);
    });

    void extractMusicMetadata(src, controller.signal)
      .then((result) => {
        if (!result) return;
        cover = result.coverUrl;
        if (controller.signal.aborted) {
          if (cover) URL.revokeObjectURL(cover);
          return;
        }
        update({ ...result, title: result.title || fileTitle(src) });
      })
      .catch(() => {});
  });

  return (
    <div class="music-track" style={{ "background-color": metadata().background ?? "#29272e" }}>
      <button
        class="music-cover"
        type="button"
        disabled={invalid() || !metadata().src}
        aria-label={`${playing() ? "pause" : "play"} ${metadata().title ?? "music"}`}
        onClick={() => {
          ensureMusicDock();
          player.play(metadata());
        }}
      >
        <Show
          when={coverUrl()}
          fallback={
            <span class="music-note" aria-hidden="true">
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
                class="lucide lucide-music"
              >
                <path d="M9 18V5l12-2v13" />
                <circle cx="6" cy="18" r="3" />
                <circle cx="18" cy="16" r="3" />
              </svg>
            </span>
          }
        >
          {(cover) => (
            <>
              <img
                src={cover()}
                alt=""
                onLoad={(event) => {
                  const src = coverUrl();
                  if (!src || sampledCover === src) {
                    return;
                  }

                  sampledCover = src;
                  const background = coverBackground(event.currentTarget);
                  if (background) {
                    update({ ...metadata(), background });
                  }
                }}
              />
              <span class="music-play-icon" aria-hidden="true">
                {playing() ? (
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
              </span>
            </>
          )}
        </Show>
      </button>
      <div class="music-divider" aria-hidden="true" />
      <div class="music-track-info">
        <div class="music-title">{metadata().title || "unknown title"}</div>
        <div class="music-artist">{metadata().artist || "unknown artist"}</div>
        <div class="music-details">
          {formatTime(active() ? player.duration() : (metadata().duration ?? 0))}
          <Show when={metadata().size}>
            {(size) => <span> · {(size() / 1048576).toFixed(2)} MiB</span>}
          </Show>
        </div>
        <Show when={invalid()}>
          <span role="alert">config error</span>
        </Show>
      </div>
    </div>
  );
}
