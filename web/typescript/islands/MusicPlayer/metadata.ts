import type { MusicMetadata } from "./types";

export async function extractMusicMetadata(
  src: string,
  signal: AbortSignal,
): Promise<MusicMetadata | undefined> {
  const [{ makeTokenizer }, { parseFromTokenizer }] = await Promise.all([
    import("@tokenizer/http"),
    import("music-metadata"),
  ]);

  if (signal.aborted) {
    return;
  }

  const tokenizer = await makeTokenizer(src);
  const close = () => {
    void tokenizer.close();
  };
  signal.addEventListener("abort", close, { once: true });

  try {
    if (signal.aborted) {
      return;
    }

    const { common, format } = await parseFromTokenizer(tokenizer);
    if (signal.aborted) {
      return;
    }

    const picture = common.picture?.[0];
    const coverUrl =
      picture && /^image\/(jpeg|png|webp|gif|avif)$/.test(picture.format)
        ? URL.createObjectURL(new Blob([new Uint8Array(picture.data)], { type: picture.format }))
        : undefined;

    return {
      src,
      title: common.title,
      artist: common.artist,
      album: common.album,
      duration: format.duration,
      size: tokenizer.fileInfo.size,
      coverUrl,
    };
  } finally {
    signal.removeEventListener("abort", close);
    await tokenizer.close();
  }
}

const MAX_BACKGROUND_LUMINANCE = 0.1;

function toLinear(channel: number) {
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function toChannel(value: number) {
  return Math.floor(
    255 * (value <= 0.0031308 ? value * 12.92 : 1.055 * value ** (1 / 2.4) - 0.055),
  );
}

export function coverBackground(img: HTMLImageElement) {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 16;

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    context.drawImage(img, 0, 0, 16, 16);

    const { data } = context.getImageData(0, 0, 16, 16);
    const rgb = [0, 0, 0];
    for (let i = 0; i < data.length; i += 4) {
      for (let c = 0; c < 3; c++) {
        rgb[c] += data[i + c];
      }
    }

    const channels = rgb.map((value) => Math.floor((value / 256) * 0.45));
    const [r, g, b] = channels.map(toLinear);
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    if (luminance <= MAX_BACKGROUND_LUMINANCE) {
      return `rgb(${channels.join(", ")})`;
    }

    const scale = MAX_BACKGROUND_LUMINANCE / luminance;
    return `rgb(${channels.map((value) => toChannel(toLinear(value) * scale)).join(", ")})`;
  } catch {
    return;
  }
}
