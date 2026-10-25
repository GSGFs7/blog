# Renderer comparison

Generated at `2026-10-25T15:46:16.307121+00:00`.  
Input: CommonMark `spec.txt` (204971 bytes).  
SHA-256: `b74aec17b162406c847fe0849aaee880c9bbba241e50e09ecb6664f13ce8a7a6`.  
Warmups: 20; iterations per repeat: 40; repeats: 9.

| Engine                      |         Version | Best ms | Median ms | Worst ms | vs fastest | HTML bytes |
| --------------------------- | --------------: | ------: | --------: | -------: | ---------: | ---------: |
| rust render in this project |       workspace |  47.288 |    47.453 |   48.251 |     26.57x |     658382 |
| markdown-it.js default      |          15.0.0 |   8.246 |     8.401 |    9.357 |      4.70x |     228449 |
| markdown-it-rs upstream     | 0.7.0 workspace |   2.418 |     2.469 |    2.614 |      1.38x |     228436 |
| cmark-gfm default           |   0.29.0.gfm.13 |   1.777 |     1.786 |    1.822 |      1.00x |     228459 |
