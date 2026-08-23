# Renderer benchmark

This benchmark renders the vendored CommonMark `spec.txt` with four engines:

- the project's Rust renderer with its complete production plugin and post-processing pipeline;
- The original `markdown-it.js` with default options;
- upstream `markdown-it-rs` with its CommonMark and HTML plugins;
- GitHub's `libcmark-gfm` with `CMARK_OPT_DEFAULT`.

```bash
./benchmark.py
```

Requirements are Rust, Node.js, a C compiler, `pkg-config`, and the `libcmark-gfm` development headers.
