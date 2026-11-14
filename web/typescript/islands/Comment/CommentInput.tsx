export function CommentInput(props: {}) {
  return (
    <div class="my-8 rounded-2xl border border-gray-600 bg-[#1a1c25]">
      <form class="relative" id="comment-form">
        <textarea
          required
          placeholder="留个评论？"
          class="min-h-36 w-full resize-none bg-transparent p-3 focus:outline-0 sm:min-h-48"
          id="content"
          name="content"
        />
      </form>

      <div class="flex items-center justify-between border-t border-gray-700">
        {/* TODO */}
        <div>{/* avatar */}</div>
        <div>{/* commit button */}</div>
      </div>
    </div>
  );
}
