import { CommentList } from "./CommentList";

export function Comment(props: Readonly<{ id?: unknown }>) {
  const postId = Number(props.id);

  return (
    <div class="mx-auto max-w-5xl">
      <div class="relative my-12 rounded-2xl border border-t border-gray-700">
        <span class="absolute top-0 left-[1%] -translate-y-4/7 text-2xl">Comment</span>
      </div>

      <CommentList postId={postId} />
    </div>
  );
}
