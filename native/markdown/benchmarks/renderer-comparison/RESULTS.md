# Renderer comparison

Generated at `2026-11-27T03:53:09.194867+00:00`.  
Input: CommonMark `spec.txt` (204971 bytes).  
SHA-256: `b74aec17b162406c847fe0849aaee880c9bbba241e50e09ecb6664f13ce8a7a6`.  
Warmups: 20; iterations per repeat: 40; repeats: 9.  
Pinned CPUs: `4`.

| Engine                        |         Version | Best ms | Median ms | Worst ms | vs fastest | HTML bytes |
| ----------------------------- | --------------: | ------: | --------: | -------: | ---------: | ---------: |
| rust renderer in this project |       workspace |  39.477 |    39.607 |   41.230 |     22.76x |     658382 |
| markdown-it.js default        |          15.0.0 |   8.143 |     8.340 |   10.683 |      4.79x |     228449 |
| markdown-it-rs upstream       | 0.7.0 workspace |   2.172 |     2.177 |    2.198 |      1.25x |     228436 |
| cmark-gfm default             |   0.29.0.gfm.13 |   1.722 |     1.740 |    1.768 |      1.00x |     228459 |
