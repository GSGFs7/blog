import argparse
import csv
import json
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

CGROUP_FILES = ["cpu.stat", "memory.current", "memory.peak", "memory.events"]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def kubectl(namespace, *args, stdin=None):
    result = subprocess.run(
        ["kubectl", "--request-timeout=10s", "-n", namespace, *args],
        input=stdin,
        text=True,
        capture_output=True,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def attempt(namespace, *args):
    started = timestamp()
    try:
        return {"time": started, "output": kubectl(namespace, *args)}
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        return {"time": started, "error": str(error)}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def summarize(output):
    groups = defaultdict(list)
    with (
        (output / "k6.log").open() as source,
        (output / "k6.jsonl").open("w") as points,
    ):
        for line in source:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") not in {"Point", "Metric"}:
                continue
            points.write(line)
            if record["type"] != "Point":
                continue
            data = record["data"]
            tags = data.get("tags") or {}
            key = (record["metric"], tags.get("name", ""), tags.get("status", ""))
            groups[key].append(data["value"])
    with (output / "k6-summary.csv").open("w") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "metric",
                "endpoint",
                "status",
                "samples",
                "sum",
                "avg",
                "p95",
                "p99",
                "max",
            ]
        )
        for key, values in sorted(groups.items()):
            values.sort()
            writer.writerow(
                [
                    *key,
                    len(values),
                    sum(values),
                    sum(values) / len(values),
                    values[int((len(values) - 1) * 0.95)],
                    values[int((len(values) - 1) * 0.99)],
                    values[-1],
                ]
            )


def capture(args):
    output = args.output or Path("artifacts/loadtest") / datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    print(f"采集目录：{output.resolve()}", flush=True)
    namespace = args.namespace
    started = timestamp()
    job = args.job
    if not job:
        job = "blog-k6-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        template = json.loads(
            kubectl(
                namespace,
                "create",
                "job",
                job,
                "--from=cronjob/blog-k6",
                "--dry-run=client",
                "-o",
                "json",
            )
        )
        container = template["spec"]["template"]["spec"]["containers"][0]
        overrides = {"K6_OUT": "json=/dev/stdout"}
        for entry in args.env:
            name, separator, value = entry.partition("=")
            if not separator or not name:
                raise ValueError("--env 必须使用 NAME=value 格式")
            overrides[name] = value
        container["env"] = [
            item for item in container.get("env", []) if item["name"] not in overrides
        ]
        container["env"].extend(
            {"name": name, "value": value} for name, value in overrides.items()
        )
        kubectl(namespace, "create", "-f", "-", stdin=json.dumps(template))
    write_json(
        output / "run.json",
        {
            "job": job,
            "namespace": namespace,
            "started": started,
            "interval": args.interval,
        },
    )
    followers = {}
    log_files = []
    seen_restarts = set()

    def follow(key, arguments, filename):
        if key in followers:
            return
        log = (output / filename).open("w")
        log_files.append(log)
        followers[key] = subprocess.Popen(
            [
                "kubectl",
                "-n",
                namespace,
                "logs",
                *arguments,
                "-f",
                "--pod-running-timeout=120s",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    def snapshot(pool):
        pods = json.loads(kubectl(namespace, "get", "pods", "-o", "json"))
        selected = [
            pod
            for pod in pods["items"]
            if pod["metadata"].get("labels", {}).get("app")
            in {"blog-django", "blog-postgres", "blog-pgbouncer", "blog-redis"}
            or pod["metadata"].get("labels", {}).get("job-name") == job
        ]
        result = {
            "time": timestamp(),
            "pods": [
                {
                    "name": pod["metadata"]["name"],
                    "uid": pod["metadata"]["uid"],
                    "node": pod["spec"].get("nodeName"),
                    "resources": {
                        c["name"]: c.get("resources", {})
                        for c in pod["spec"]["containers"]
                    },
                    "status": pod["status"],
                }
                for pod in selected
            ],
        }
        tasks = {
            "usage": pool.submit(
                attempt,
                namespace,
                "get",
                "--raw",
                f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods",
            ),
            "hpa": pool.submit(attempt, namespace, "get", "hpa", "-o", "json"),
        }
        for pod in selected:
            name = pod["metadata"]["name"]
            if pod["metadata"].get("labels", {}).get("job-name") == job:
                follow("k6", [name, "-c", "k6"], "k6.log")
                continue
            for status in pod["status"].get("containerStatuses", []):
                container = status["name"]
                restarts = status.get("restartCount", 0)
                key = (pod["metadata"]["uid"], container, restarts)
                if status.get("state", {}).get("running"):
                    follow(
                        key,
                        [
                            name,
                            "-c",
                            container,
                            "--since-time=" + started,
                            "--timestamps",
                        ],
                        f"{name}-{container}-{restarts}.log",
                    )
                if restarts and key not in seen_restarts:
                    seen_restarts.add(key)
                    tasks[f"previous-{name}-{container}-{restarts}"] = pool.submit(
                        attempt,
                        namespace,
                        "logs",
                        name,
                        "-c",
                        container,
                        "--previous",
                        "--timestamps",
                        "--since-time=" + started,
                    )
            if pod["metadata"].get("labels", {}).get("app") == "blog-django":
                tasks[f"cgroup-{name}"] = pool.submit(
                    attempt,
                    namespace,
                    "exec",
                    name,
                    "-c",
                    "blog-django",
                    "--",
                    "cat",
                    *[f"/sys/fs/cgroup/{file}" for file in CGROUP_FILES],
                )
                tasks[f"django-{name}"] = pool.submit(
                    attempt,
                    namespace,
                    "get",
                    "--raw",
                    f"/api/v1/namespaces/{namespace}/pods/{name}:8000/proxy/prometheus/metrics",
                )
        result["samples"] = {name: future.result() for name, future in tasks.items()}
        with (output / "snapshots.jsonl").open("a") as target:
            target.write(json.dumps(result, ensure_ascii=False) + "\n")

    outcome = "timeout"
    capture_error = None
    try:
        deadline = time.monotonic() + args.timeout
        with ThreadPoolExecutor(max_workers=8) as pool:
            while time.monotonic() < deadline:
                tick = time.monotonic()
                snapshot(pool)
                state = json.loads(kubectl(namespace, "get", "job", job, "-o", "json"))
                write_json(output / "job.json", state)
                conditions = state.get("status", {}).get("conditions", [])
                terminal = next(
                    (
                        item["type"]
                        for item in conditions
                        if item["type"] in {"Complete", "Failed"}
                        and item["status"] == "True"
                    ),
                    None,
                )
                if terminal:
                    outcome = terminal
                    break
                time.sleep(max(0, args.interval - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        outcome = "interrupted"
    except Exception as error:
        outcome = "error"
        capture_error = str(error)
        raise
    finally:
        if "k6" in followers:
            try:
                followers["k6"].wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        stopped_by_collector = []
        for key, process in followers.items():
            if process.poll() is None:
                stopped_by_collector.append(str(key))
                process.terminate()
        for process in followers.values():
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in log_files:
            log.close()
        write_json(
            output / "events.json", attempt(namespace, "get", "events", "-o", "json")
        )
        write_json(
            output / "result.json",
            {
                "job": job,
                "outcome": outcome,
                "capture_error": capture_error,
                "finished": timestamp(),
                "stopped_by_collector": stopped_by_collector,
                "log_exit_codes": {
                    str(key): process.returncode for key, process in followers.items()
                },
            },
        )
        if (output / "k6.log").exists():
            summarize(output)
        print(f"采集结束：{outcome}；结果保存在 {output.resolve()}。", flush=True)
    return 0 if outcome == "Complete" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="blog")
    parser.add_argument(
        "--job", help="仅采集已有 Job；省略时从 blog-k6 CronJob 创建新 Job"
    )
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=1800)
    arguments = parser.parse_args()
    if arguments.interval <= 0 or arguments.timeout <= 0:
        parser.error("--interval 和 --timeout 必须大于 0")
    if arguments.job and arguments.env:
        parser.error("--job 不能与 --env 同时使用")
    raise SystemExit(capture(arguments))
