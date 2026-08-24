import { makeTokenizer } from "@tokenizer/http";
import { parseFromTokenizer } from "music-metadata";

export async function extractMusicMetadata(url: string) {
  try {
    const httpTokenizer = await makeTokenizer(url);
    const { common, format } = await parseFromTokenizer(httpTokenizer);

    const picture = common.picture?.[0];
    return {
      title: common.title,
      artist: common.artist,
      album: common.album,
      duration: format.duration,
      size: httpTokenizer.fileInfo.size,
      coverData: picture?.data,
      coverMimeType: picture?.format,
      bitrate: format.bitrate,
      sampleRate: format.sampleRate,
      src: url,
    };
  } catch (e) {
    console.error("[Music] Failed extract music metadata: ", e);
  }
}
