# Renderer comparison

Generated at `2026-11-22T01:53:09.469920+00:00`.  
Input: CommonMark `spec.txt` (204971 bytes).  
SHA-256: `b74aec17b162406c847fe0849aaee880c9bbba241e50e09ecb6664f13ce8a7a6`.  
Warmups: 20; iterations per repeat: 40; repeats: 9.  
Pinned CPUs: `2`.

| Engine                        |         Version | Best ms | Median ms | Worst ms | vs fastest | HTML bytes |
| ----------------------------- | --------------: | ------: | --------: | -------: | ---------: | ---------: |
| rust renderer in this project |       workspace |  40.276 |    41.218 |   41.543 |     23.31x |     658382 |
| markdown-it.js default        |          15.0.0 |   8.428 |     8.550 |   11.093 |      4.84x |     228449 |
| markdown-it-rs upstream       | 0.7.0 workspace |   2.448 |     2.468 |    2.482 |      1.40x |     228436 |
| cmark-gfm default             |   0.29.0.gfm.13 |   1.756 |     1.768 |    1.823 |      1.00x |     228459 |
