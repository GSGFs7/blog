export function formatTime(seconds: number) {
  const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

export function musicSource(value: unknown): string | undefined {
  if (typeof value !== "string" || !value.trim()) {
    return;
  }

  try {
    const url = new URL(value, document.baseURI);
    if (["http:", "https:"].includes(url.protocol)) {
      return url.href;
    }
  } catch {}
}

export function fileTitle(src: string) {
  try {
    return decodeURIComponent(new URL(src).pathname.split("/").pop() || "untitled track");
  } catch {
    return "untitled track";
  }
}
