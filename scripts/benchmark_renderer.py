#!/usr/bin/env python

import argparse
import gc
import logging
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from ipaddress import ip_address
from pathlib import Path
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    payload: Any


def configure_django() -> tuple[Any, ...]:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blog.settings")

    import django
    from django.test import Client, RequestFactory, override_settings
    from django.utils.translation import gettext_lazy
    from ninja.renderers import JSONRenderer
    from pydantic import AnyUrl, BaseModel

    django.setup()
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    from api.urls import UltraSpeedJSONRender, api

    return (
        Client,
        RequestFactory,
        JSONRenderer,
        UltraSpeedJSONRender,
        gettext_lazy,
        AnyUrl,
        BaseModel,
        override_settings,
        api,
    )


def build_cases(
    gettext_lazy: Any, any_url: Any, base_model: Any
) -> list[BenchmarkCase]:
    class ExampleModel(base_model):
        value: int

    class ExampleUrl(base_model):
        url: any_url

    timestamp = datetime(2026, 7, 7, 1, 2, 3, 456789, tzinfo=timezone.utc)
    post_cards = [
        {
            "id": index,
            "title": f"post {index}",
            "slug": f"post-{index}",
            "meta_description": "x" * 120,
            "cover_image": f"https://example.com/image/{index}.png",
            "created_at": timestamp,
            "updated_at": timestamp,
            "content_update_at": timestamp,
            "category": {"id": 1, "name": "tech"},
            "tags": [{"id": tag, "name": f"tag-{tag}"} for tag in range(5)],
        }
        for index in range(1000)
    ]
    comments = {
        "comments": [
            {
                "id": index,
                "content": "hello" * 20,
                "post_id": 1,
                "guest_id": index,
                "guest_name": f"user-{index}",
                "created_at": timestamp,
                "updated_at": timestamp,
                "avatar": "https://example.com/avatar.png",
            }
            for index in range(1000)
        ]
    }
    compat_types = {
        "decimal": Decimal("1.23"),
        "ip": ip_address("127.0.0.1"),
        "lazy": gettext_lazy("hello"),
        "model": ExampleModel(value=1),
        "url": ExampleUrl(url="https://example.com/path").url,
    }
    small_message = {"message": "OK"}

    return [
        BenchmarkCase("small_message", small_message),
        BenchmarkCase("post_cards_1000", post_cards),
        BenchmarkCase("comments_1000", comments),
        BenchmarkCase("compat_types", compat_types),
    ]


def run_once(
    renderer: Any,
    request: Any,
    payload: Any,
    iterations: int,
) -> tuple[float, int]:
    total_bytes = 0
    started_at = perf_counter()
    for _ in range(iterations):
        content = renderer.render(request, payload, response_status=200)
        total_bytes += len(content)
    elapsed = perf_counter() - started_at
    return elapsed, total_bytes // iterations


def benchmark(
    renderer: Any,
    request: Any,
    payload: Any,
    *,
    iterations: int,
    repeats: int,
) -> tuple[float, float, int]:
    run_once(renderer, request, payload, max(1, iterations // 10))
    timings = []
    old_gc_state = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            elapsed, payload_size = run_once(renderer, request, payload, iterations)
            timings.append(elapsed / iterations)
    finally:
        if old_gc_state:
            gc.enable()
    return min(timings), statistics.median(timings), payload_size


def parse_headers(values: list[str]) -> dict[str, str]:
    headers = {}
    for value in values:
        if ":" not in value:
            raise ValueError(f"Invalid header {value!r}, expected 'Name: value'")
        name, header_value = value.split(":", 1)
        headers[name.strip()] = header_value.strip()
    return headers


def run_endpoint_once(
    client: Any,
    method: str,
    path: str,
    headers: dict[str, str],
    expected_status: int,
    iterations: int,
) -> tuple[float, int]:
    request = getattr(client, method)
    total_bytes = 0
    started_at = perf_counter()
    for _ in range(iterations):
        response = request(path, headers=headers)
        if response.status_code != expected_status:
            raise RuntimeError(
                f"{method.upper()} {path} returned {response.status_code}, "
                f"expected {expected_status}"
            )
        total_bytes += len(response.content)
    elapsed = perf_counter() - started_at
    return elapsed, total_bytes // iterations


def benchmark_endpoint(
    api: Any,
    renderer: Any,
    client: Any,
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    expected_status: int,
    iterations: int,
    repeats: int,
) -> tuple[float, float, int]:
    previous_renderer = api.renderer
    api.renderer = renderer
    try:
        run_endpoint_once(
            client,
            method,
            path,
            headers,
            expected_status,
            max(1, iterations // 10),
        )
        timings = []
        old_gc_state = gc.isenabled()
        gc.disable()
        try:
            for _ in range(repeats):
                elapsed, payload_size = run_endpoint_once(
                    client,
                    method,
                    path,
                    headers,
                    expected_status,
                    iterations,
                )
                timings.append(elapsed / iterations)
        finally:
            if old_gc_state:
                gc.enable()
        return min(timings), statistics.median(timings), payload_size
    finally:
        api.renderer = previous_renderer


def print_result_header() -> None:
    print(
        f"{'case':<18} {'renderer':<8} {'best ms':>10} "
        f"{'median ms':>10} {'ops/s':>12} {'bytes':>10} {'speedup':>9}"
    )
    print("-" * 85)


def print_result(
    case_name: str,
    renderer_name: str,
    best: float,
    median: float,
    payload_size: int,
    speedup: str = "",
) -> None:
    print(
        f"{case_name:<18} {renderer_name:<8} {best * 1000:10.4f} "
        f"{median * 1000:10.4f} {1 / best:12.0f} "
        f"{payload_size:10d} {speedup:>9}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument(
        "--mode",
        choices=["render", "endpoint", "both"],
        default="render",
    )
    parser.add_argument("--endpoint", default="/api/health")
    parser.add_argument("--method", choices=["get"], default="get")
    parser.add_argument("--expected-status", type=int, default=200)
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="HTTP header in 'Name: value' form. Can be passed multiple times.",
    )
    args = parser.parse_args()

    (
        client_class,
        request_factory,
        json_renderer,
        ultra_speed_json_render,
        gettext_lazy,
        any_url,
        base_model,
        override_settings,
        api,
    ) = configure_django()
    request = request_factory().get("/api/benchmark")
    renderers = {
        "ninja": json_renderer(),
        "orjson": ultra_speed_json_render(),
    }

    print(f"iterations={args.iterations} repeats={args.repeats}")

    if args.mode in {"render", "both"}:
        print("\nrender benchmark")
        print_result_header()
        for case in build_cases(gettext_lazy, any_url, base_model):
            results = {}
            for name, renderer in renderers.items():
                best, median, payload_size = benchmark(
                    renderer,
                    request,
                    case.payload,
                    iterations=args.iterations,
                    repeats=args.repeats,
                )
                results[name] = best
                speedup = ""
                if name != "ninja":
                    speedup = f"{results['ninja'] / best:.2f}x"
                print_result(case.name, name, best, median, payload_size, speedup)
            print()

    if args.mode in {"endpoint", "both"}:
        headers = parse_headers(args.header)
        client = client_class()
        print(f"\nendpoint benchmark: {args.method.upper()} {args.endpoint}")
        print_result_header()
        with override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"]):
            results = {}
            for name, renderer in renderers.items():
                best, median, payload_size = benchmark_endpoint(
                    api,
                    renderer,
                    client,
                    method=args.method,
                    path=args.endpoint,
                    headers=headers,
                    expected_status=args.expected_status,
                    iterations=args.iterations,
                    repeats=args.repeats,
                )
                results[name] = best
                speedup = ""
                if name != "ninja":
                    speedup = f"{results['ninja'] / best:.2f}x"
                print_result("endpoint", name, best, median, payload_size, speedup)


if __name__ == "__main__":
    main()
