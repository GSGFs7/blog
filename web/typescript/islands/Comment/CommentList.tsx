import { createMemo, For, Loading, onCleanup } from "solid-js";

import { CommentListItem } from "./schema";

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
              <img
                alt={`${comment.guest_name}'s avatar`}
                class="size-10 rounded-full object-cover"
                width={40}
                height={40}
                src={comment.avatar}
              />
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
