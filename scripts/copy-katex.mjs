import fs from "node:fs";
import path from "node:path";

const srcDir = path.join("node_modules", "katex", "dist");
const destDir = path.join("web", "static", "katex");

const filesToCopy = ["katex.min.css", "fonts"];

try {
  if (!fs.existsSync(destDir)) {
    fs.mkdirSync(destDir, { recursive: true });
  }

  for (const file of filesToCopy) {
    const src = path.join(srcDir, file);
    const dest = path.join(destDir, file);

    if (fs.existsSync(src)) {
      fs.cpSync(src, dest, { recursive: true, force: true });
      console.log(`Successfully copied ${file} to ${destDir}`);
    } else {
      console.error(`Source not found: ${src}`);
      process.exit(1);
    }
  }
} catch (err) {
  console.error(`Error copying KaTeX assets: ${err.message}`);
  process.exit(1);
}
