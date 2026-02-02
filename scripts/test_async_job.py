import argparse
import time
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Test OCR async jobs.")
    parser.add_argument("file", type=Path, help="Path to PDF/JPG/PNG file.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--document-type", default="auto")
    parser.add_argument("--language", default="pt-BR")
    parser.add_argument("--preserve-layout", action="store_true")
    parser.add_argument("--quality-threshold", type=float, default=0.8)
    parser.add_argument("--poll-interval", type=float, default=1.5)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")

    endpoint = f"{args.base_url}/api/v1/ocr/extract-async"
    with args.file.open("rb") as file_handle:
        files = {"file": (args.file.name, file_handle)}
        data = {
            "document_type": args.document_type,
            "language": args.language,
            "preserve_layout": "true" if args.preserve_layout else "false",
            "quality_threshold": str(args.quality_threshold),
        }
        response = requests.post(endpoint, files=files, data=data, timeout=30)

    response.raise_for_status()
    payload = response.json()
    job_id = payload.get("job_id")
    if not job_id:
        raise SystemExit(f"Missing job_id in response: {payload}")

    print(f"job_id: {job_id}")

    status_endpoint = f"{args.base_url}/api/v1/ocr/jobs/{job_id}"
    start_time = time.time()
    while True:
        status_response = requests.get(status_endpoint, timeout=30)
        status_response.raise_for_status()
        status_payload = status_response.json()
        status = status_payload.get("status")
        print(f"status: {status}")
        if status in {"SUCCESS", "FAILED"}:
            print(status_payload)
            break
        if time.time() - start_time > args.timeout:
            raise SystemExit("Timed out waiting for job completion.")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
