#!/usr/bin/env python

import argparse
import os
import sys
from pathlib import Path

import dotenv


def upload_file(path: Path, bucket: str, prefix: str) -> None:
    import boto3

    key = f"{prefix.strip('/')}/{path.name}" if prefix.strip("/") else path.name
    print(f"Uploading: {path} -> s3://{bucket}/{key}")
    with boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name="auto",
    ) as client:
        client.upload_file(str(path), bucket, key)
    print("Backup uploaded successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a database backup to R2")
    subparsers = parser.add_subparsers(dest="command", required=True)
    upload = subparsers.add_parser("upload")
    upload.add_argument("path", type=Path)
    upload.add_argument("bucket")
    upload.add_argument("prefix", nargs="?", default="")
    args = parser.parse_args()

    dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if not args.path.is_file():
        print(f"Backup file does not exist: {args.path}", file=sys.stderr)
        return 1

    try:
        upload_file(args.path, args.bucket, args.prefix)
    except Exception as error:
        print(f"Backup upload failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
