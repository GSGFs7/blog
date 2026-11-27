import { fireEvent, render, screen } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";

import { CommentList } from "./CommentList";

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders image when avatar exists and fallback initial when avatar is empty", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        comments: [
          {
            id: 1,
            content: "<p>With avatar</p>",
            post_id: 7,
            guest_id: "00000000-0000-0000-0000-000000000001",
            guest_name: "Alice",
            created_at: "2026-11-27T00:00:00Z",
            updated_at: "2026-11-27T00:00:00Z",
            avatar: "https://img.gsgfs.moe/avatars/aa/bb/aabb.webp",
          },
          {
            id: 2,
            content: "<p>Without avatar</p>",
            post_id: 7,
            guest_id: "00000000-0000-0000-0000-000000000002",
            guest_name: "bob",
            created_at: "2026-11-27T00:00:00Z",
            updated_at: "2026-11-27T00:00:00Z",
            avatar: "",
          },
          {
            id: 3,
            content: "<p>Whitespace avatar</p>",
            post_id: 7,
            guest_id: "00000000-0000-0000-0000-000000000003",
            guest_name: "   ",
            created_at: "2026-11-27T00:00:00Z",
            updated_at: "2026-11-27T00:00:00Z",
            avatar: "   ",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(() => <CommentList postId={7} />);

  const avatarImg = await screen.findByAltText("Alice's avatar");
  expect(avatarImg).toHaveAttribute("src", "https://img.gsgfs.moe/avatars/aa/bb/aabb.webp");

  expect(screen.getAllByRole("img")).toHaveLength(1);
  expect(screen.queryByAltText("bob's avatar")).not.toBeInTheDocument();
  expect(screen.getByText("B")).toBeInTheDocument();
  expect(screen.getByText("?")).toBeInTheDocument();

  fireEvent.error(avatarImg);
  flush();

  expect(screen.queryByAltText("Alice's avatar")).not.toBeInTheDocument();
  expect(screen.getByText("A")).toBeInTheDocument();
});
