import fs from "node:fs";
import { performance } from "node:perf_hooks";

import MarkdownIt from "markdown-it";

const [sourcePath, warmupsArg, iterationsArg, repeatsArg] = process.argv.slice(2);
const warmups = Number.parseInt(warmupsArg, 10);
const iterations = Number.parseInt(iterationsArg, 10);
const repeats = Number.parseInt(repeatsArg, 10);
const source = fs.readFileSync(sourcePath, "utf8");
const markdown = new MarkdownIt();

let outputBytes = 0;
for (let index = 0; index < warmups; index += 1) {
  outputBytes = Buffer.byteLength(markdown.render(source));
}

const samplesMs = [];
let checksum = 0;
for (let repeat = 0; repeat < repeats; repeat += 1) {
  const startedAt = performance.now();
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const output = markdown.render(source);
    outputBytes = Buffer.byteLength(output);
    checksum += outputBytes;
  }
  samplesMs.push((performance.now() - startedAt) / iterations);
}

process.stdout.write(
  JSON.stringify({
    engine: "markdown-it.js default",
    version: "15.0.0",
    samples_ms: samplesMs,
    output_bytes: outputBytes,
    checksum,
  }),
);
