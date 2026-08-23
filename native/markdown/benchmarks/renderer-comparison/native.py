import json
import sys
import time
from pathlib import Path

from markdown_it_rs_py import MarkdownIt

source_path, warmups_arg, iterations_arg, repeats_arg = sys.argv[1:]
warmups = int(warmups_arg)
iterations = int(iterations_arg)
repeats = int(repeats_arg)
source = Path(source_path).read_text()
markdown = MarkdownIt()

output_bytes = 0
for _ in range(warmups):
    output_bytes = len(markdown.prepare(source).finish().encode())

samples_ms = []
checksum = 0
for _ in range(repeats):
    started_at = time.perf_counter()
    for _ in range(iterations):
        output = markdown.prepare(source).finish()
        output_bytes = len(output.encode())
        checksum += output_bytes
    samples_ms.append((time.perf_counter() - started_at) * 1000 / iterations)

print(
    json.dumps(
        {
            "engine": "rust render in this project",
            "version": "workspace",
            "samples_ms": samples_ms,
            "output_bytes": output_bytes,
            "checksum": checksum,
        }
    )
)
