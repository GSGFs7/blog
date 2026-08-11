import argparse
import gc
import math
import platform
import statistics
import time

import _crc64nvme

DEFAULT_SIZES = (
    0,
    1,
    7,
    8,
    31,
    64,
    256,
    1024,
    8 * 1024,
    64 * 1024,
    1024 * 1024,
    16 * 1024 * 1024,
    64 * 1024 * 1024,
)
SIZE_SUFFIXES = {
    "gib": 1024**3,
    "mib": 1024**2,
    "kib": 1024,
    "gb": 1000**3,
    "mb": 1000**2,
    "kb": 1000,
    "b": 1,
}


def parse_size(value):
    normalized = value.strip().lower().replace("_", "")
    for suffix, multiplier in SIZE_SUFFIXES.items():
        if normalized.endswith(suffix):
            number = normalized[: -len(suffix)]
            break
    else:
        number = normalized
        multiplier = 1

    try:
        size = int(number, 0) * multiplier
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid size: {value}") from error

    if size < 0:
        raise argparse.ArgumentTypeError("size must not be negative")
    return size


def positive_int(value):
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if result < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return result


def positive_float(value):
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a number") from error
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return result


def format_size(size):
    for divisor, suffix in (
        (1024**3, "GiB"),
        (1024**2, "MiB"),
        (1024, "KiB"),
    ):
        if size >= divisor and size % divisor == 0:
            return f"{size // divisor} {suffix}"
    return f"{size} B"


def format_duration(nanoseconds):
    if nanoseconds < 1_000:
        return f"{nanoseconds:.1f} ns"
    if nanoseconds < 1_000_000:
        return f"{nanoseconds / 1_000:.2f} us"
    return f"{nanoseconds / 1_000_000:.2f} ms"


def run_batch(data, iterations):
    checksum = 0
    start = time.perf_counter_ns()
    for _ in range(iterations):
        checksum ^= _crc64nvme.crc64nvme(data)
    elapsed = time.perf_counter_ns() - start
    return elapsed, checksum


def calibrate(data, target_ns, max_iterations):
    iterations = 1
    while True:
        elapsed, _ = run_batch(data, iterations)
        if elapsed >= target_ns or iterations == max_iterations:
            return iterations

        scale = max(2, min(1000, math.ceil(target_ns / max(elapsed, 1))))
        iterations = min(max_iterations, iterations * scale)


def benchmark(data, rounds, target_ns, max_iterations):
    _crc64nvme.crc64nvme(data)
    iterations = calibrate(data, target_ns, max_iterations)
    samples = [run_batch(data, iterations)[0] / iterations for _ in range(rounds)]
    median = statistics.median(samples)
    deviation = statistics.median(abs(sample - median) for sample in samples)
    return iterations, median, deviation / median * 100 if median else 0


def create_parser():
    parser = argparse.ArgumentParser(
        description="Benchmark the installed CRC-64/NVME native extension."
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=parse_size,
        default=DEFAULT_SIZES,
        metavar="SIZE",
        help="input sizes in bytes or with KiB/MiB/GiB suffixes",
    )
    parser.add_argument(
        "--rounds",
        type=positive_int,
        default=7,
        help="number of measured batches per input size (default: 7)",
    )
    parser.add_argument(
        "--target-ms",
        type=positive_float,
        default=100.0,
        help="minimum duration of each measured batch (default: 100)",
    )
    parser.add_argument(
        "--max-iterations",
        type=positive_int,
        default=5_000_000,
        help="maximum calls per measured batch (default: 5000000)",
    )
    return parser


def main():
    args = create_parser().parse_args()
    expected = 0xAE8B14860A799888
    actual = _crc64nvme.crc64nvme(b"123456789")
    if actual != expected:
        raise RuntimeError(f"CRC self-check failed: {actual:#018x} != {expected:#018x}")

    print(f"Python: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"Extension: {_crc64nvme.__file__}")
    print(f"Rounds: {args.rounds}, target: {args.target_ms:g} ms per batch")
    print()
    header = "{:>10} {:>12} {:>12} {:>14} {:>8}"
    print(header.format("size", "iterations", "latency", "throughput", "MAD"))

    pattern = bytes(range(256))
    gc.disable()
    try:
        for size in args.sizes:
            data = (pattern * math.ceil(size / len(pattern)))[:size]
            iterations, latency_ns, deviation = benchmark(
                data,
                args.rounds,
                args.target_ms * 1_000_000,
                args.max_iterations,
            )
            throughput = size / latency_ns * 1e9 / 1024**3 if size else 0
            print(
                f"{format_size(size):>10} {iterations:>12,} "
                f"{format_duration(latency_ns):>12} "
                f"{throughput:>10.3f} GiB/s {deviation:>7.2f}%"
            )
    finally:
        gc.enable()


if __name__ == "__main__":
    main()
