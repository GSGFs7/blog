import { createMemo, createSignal, For, Loading, onCleanup, Show } from "solid-js";

import { CommentListItem } from "./schema";

function avatarInitial(name: string): string {
  const first = Array.from(name.trim())[0];
  return first ? first.toUpperCase() : "?";
}

function CommentAvatar(props: { avatar: string; guestName: string }) {
  const [failedSrc, setFailedSrc] = createSignal<string | null>(null);
  const src = createMemo(() => props.avatar.trim());

  return (
    <Show
      when={src() !== "" && failedSrc() !== src()}
      fallback={
        <div
          aria-hidden="true"
          class="flex size-10 items-center justify-center rounded-full bg-gray-700 text-sm font-medium text-gray-200 select-none"
        >
          {avatarInitial(props.guestName)}
        </div>
      }
    >
      <img
        alt={`${props.guestName}'s avatar`}
        class="size-10 rounded-full object-cover"
        width={40}
        height={40}
        src={src()}
        onError={() => setFailedSrc(src())}
      />
    </Show>
  );
}

export function CommentList(props: { postId: number }) {
  const comments = createMemo(async () => {
    const postId = props.postId;
    const controller = new AbortController();
    onCleanup(() => controller.abort());

    try {
      const resp = await fetch(`/api/comment/post/${postId}/all`, {
        signal: controller.signal,
      });
      if (!resp.ok) {
        console.error("[Comment]: fetch error", resp.status);
        return [] as CommentListItem[];
      }

      const data = (await resp.json()) as { comments: CommentListItem[] };
      return data.comments;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return [] as CommentListItem[];
      }

      console.error("[Comment]: fetch error", err);
      return [] as CommentListItem[];
    }
  });

  return (
    <Loading fallback={null}>
      <For each={comments()}>
        {(comment) => (
          <div class="my-4 flex w-full items-start">
            <div class="flex w-24 shrink-0 flex-col items-center gap-1 py-1">
              <CommentAvatar avatar={comment.avatar} guestName={comment.guest_name} />
              <div class="group relative w-full px-2 text-center text-sm">{comment.guest_name}</div>
            </div>

            <div class="flex min-w-0 flex-1 flex-col justify-center self-stretch border-l-2 border-gray-600/80 px-4 py-2">
              <div class="wrap-break-word" innerHTML={comment.content} />
            </div>
          </div>
        )}
      </For>
    </Loading>
  );
}
