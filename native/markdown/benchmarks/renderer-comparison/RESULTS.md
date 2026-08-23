# Renderer comparison

Generated at `2026-08-23T14:18:03.477937+00:00`.  
Input: CommonMark `spec.txt` (204971 bytes).  
SHA-256: `b74aec17b162406c847fe0849aaee880c9bbba241e50e09ecb6664f13ce8a7a6`.  
Warmups: 5; iterations per repeat: 20; repeats: 9.

| Engine                      |         Version | Best ms | Median ms | Worst ms | vs fastest | HTML bytes |
| --------------------------- | --------------: | ------: | --------: | -------: | ---------: | ---------: |
| rust render in this project |       workspace |  49.582 |    49.896 |   50.063 |     29.58x |     658304 |
| markdown-it.js default      |          15.0.0 |   8.104 |     8.184 |   10.065 |      4.85x |     228449 |
| markdown-it-rs upstream     | 0.7.0 workspace |   3.732 |     3.770 |    3.802 |      2.24x |     228436 |
| cmark-gfm default           |   0.29.0.gfm.13 |   1.680 |     1.687 |    1.721 |      1.00x |     228459 |
