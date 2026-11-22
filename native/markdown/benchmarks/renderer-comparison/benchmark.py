#!/usr/bin/env python

import argparse
import datetime
import hashlib
import json
import os
import shutil
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "spec.txt"
BUILD = ROOT / ".build"


def parse_cpus(spec: str) -> list[int]:
    cpus: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            raise ValueError(f"invalid CPU specification: {spec!r}")
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start < 0 or end < start:
                raise ValueError(f"invalid CPU range: {token!r}")
            cpus.update(range(start, end + 1))
        else:
            cpu = int(token)
            if cpu < 0:
                raise ValueError(f"invalid CPU index: {token!r}")
            cpus.add(cpu)
    return sorted(cpus)


def resolve_cpu_affinity(spec: str) -> list[int]:
    if not hasattr(os, "sched_setaffinity") or not hasattr(os, "sched_getaffinity"):
        raise SystemExit("--cpu is only supported on platforms with sched_setaffinity")
    try:
        cpus = parse_cpus(spec)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    available = os.sched_getaffinity(0)
    unavailable = [cpu for cpu in cpus if cpu not in available]
    if unavailable:
        raise SystemExit(
            f"unavailable CPU(s): {unavailable}; available: {sorted(available)}"
        )
    return cpus


def run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def compile_cmark() -> Path:
    BUILD.mkdir(exist_ok=True)
    executable = BUILD / "cmark-gfm"
    flags = run(["pkg-config", "--cflags", "--libs", "libcmark-gfm"]).split()
    subprocess.run(
        [
            "cc",
            "-O3",
            "-DNDEBUG",
            str(ROOT / "cmark-gfm.c"),
            *flags,
            "-o",
            str(executable),
        ],
        check=True,
    )
    return executable


def compile_upstream() -> Path:
    BUILD.mkdir(exist_ok=True)
    cargo_target = BUILD / "cargo-target"
    subprocess.run(
        [
            shutil.which("cargo") or "cargo",
            "build",
            "--release",
            "--manifest-path",
            str(ROOT / "Cargo.toml"),
            "--target-dir",
            str(cargo_target),
        ],
        check=True,
    )
    return cargo_target / "release" / "renderer-comparison-upstream"


def result(command: list[str]) -> dict[str, object]:
    value = json.loads(run(command))
    samples = value.pop("samples_ms")
    value["best_ms"] = min(samples)
    value["median_ms"] = statistics.median(samples)
    value["worst_ms"] = max(samples)
    return value


def markdown_report(payload: dict[str, object]) -> str:
    rows = []
    fastest = min(item["median_ms"] for item in payload["results"])
    for item in payload["results"]:
        rows.append(
            f"| {item['engine']} | {item['version']} | {item['best_ms']:.3f} | "
            f"{item['median_ms']:.3f} | {item['worst_ms']:.3f} | "
            f"{item['median_ms'] / fastest:.2f}x | {item['output_bytes']} |"
        )
    header = [
        "# Renderer comparison  ",
        "",
        f"Generated at `{payload['generated_at']}`.  ",
        f"Input: CommonMark `spec.txt` ({payload['input_bytes']} bytes).  ",
        f"SHA-256: `{payload['input_sha256']}`.  ",
        f"Warmups: {payload['warmups']};  "
        f"iterations per repeat: {payload['iterations']};  "
        f"repeats: {payload['repeats']}.  ",
    ]
    if payload.get("pinned_cpus"):
        pinned = ", ".join(str(cpu) for cpu in payload["pinned_cpus"])
        header.append(f"Pinned CPUs: `{pinned}`.  ")
    return "\n".join(
        [
            *header,
            "",
            "| Engine | Version | Best ms | Median ms | Worst ms | "
            "vs fastest | HTML bytes |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *rows,
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument(
        "--cpu",
        type=str,
        default=None,
        help="Pin benchmark processes to CPU(s), e.g. 2 or 2,3 or 2-3",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "RESULTS.md")
    args = parser.parse_args()

    pinned_cpus = resolve_cpu_affinity(args.cpu) if args.cpu is not None else None

    if not SPEC.exists():
        raise SystemExit(f"missing benchmark input: {SPEC}")
    if not (ROOT / "node_modules" / "markdown-it").exists():
        raise SystemExit(f"run `pnpm install --dir {ROOT}` first")

    cmark = compile_cmark()
    upstream = compile_upstream()
    if pinned_cpus is not None:
        os.sched_setaffinity(0, set(pinned_cpus))
    common = [
        str(SPEC),
        str(args.warmups),
        str(args.iterations),
        str(args.repeats),
    ]
    results = [
        result(
            [
                shutil.which("python") or "python",
                str(ROOT / "native.py"),
                *common,
            ]
        ),
        result(
            [
                shutil.which("node") or "node",
                str(ROOT / "markdown-it.mjs"),
                *common,
            ]
        ),
        result([str(upstream), *common]),
        result([str(cmark), *common]),
    ]
    payload = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "cpu_count": os.cpu_count(),
        "pinned_cpus": pinned_cpus,
        "input_bytes": SPEC.stat().st_size,
        "input_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "warmups": args.warmups,
        "iterations": args.iterations,
        "repeats": args.repeats,
        "results": results,
    }
    args.output.write_text(markdown_report(payload))
    print(args.output)


if __name__ == "__main__":
    main()
