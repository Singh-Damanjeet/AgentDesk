#!/usr/bin/env python3
"""Load the checked-in AcmeFlow documents through the public ingestion API."""

from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path
from typing import Final

import httpx


DEFAULT_BASE_URL: Final[str] = "http://127.0.0.1:8000"
SUPPORTED_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".pdf", ".docx", ".txt", ".md", ".markdown"}
)
DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload the AcmeFlow demo knowledge corpus through AgentDesk."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTDESK_API_URL", DEFAULT_BASE_URL),
        help="AgentDesk backend URL (default: %(default)s)",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("samples/demo-company"),
        help="Directory containing supported demo documents.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing documents with matching filenames before upload.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List documents without changing AgentDesk.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-request timeout in seconds (default: %(default)s).",
    )
    return parser.parse_args()


def discover_documents(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise SystemExit(f"Sample directory does not exist: {directory}")

    documents = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not documents:
        raise SystemExit(f"No supported documents found in {directory}")
    return documents


def get_existing_documents(
    client: httpx.Client,
) -> dict[str, list[str]]:
    response = client.get("/api/knowledge/documents")
    response.raise_for_status()
    documents = response.json()
    existing: dict[str, list[str]] = {}
    for document in documents:
        filename = document.get("original_filename") or document.get("filename")
        document_id = document.get("id")
        if isinstance(filename, str) and isinstance(document_id, str):
            existing.setdefault(filename, []).append(document_id)
    return existing


def delete_existing(
    client: httpx.Client,
    document_ids: list[str],
    filename: str,
) -> None:
    for document_id in document_ids:
        response = client.delete(f"/api/knowledge/documents/{document_id}")
        response.raise_for_status()
        print(f"  replaced {filename} ({document_id})")


def upload_document(client: httpx.Client, path: Path) -> dict[str, object]:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as source:
        response = client.post(
            "/api/knowledge/documents",
            files={"file": (path.name, source, content_type)},
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected upload response for {path.name}")
    return payload


def main() -> int:
    args = parse_args()
    documents = discover_documents(args.directory)
    base_url = args.base_url.rstrip("/")

    print(f"Found {len(documents)} supported demo documents in {args.directory}.")
    if args.dry_run:
        for path in documents:
            print(f"  {path.name}")
        return 0

    try:
        with httpx.Client(base_url=base_url, timeout=args.timeout) as client:
            existing = get_existing_documents(client)
            for path in documents:
                matching_ids = existing.get(path.name, [])
                if matching_ids and not args.replace:
                    print(f"  skipped {path.name} (already indexed)")
                    continue

                if matching_ids:
                    delete_existing(client, matching_ids, path.name)

                payload = upload_document(client, path)
                status = payload.get("status", "unknown")
                chunks = payload.get("chunk_count", "unknown")
                print(f"  indexed {path.name}: status={status}, chunks={chunks}")
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500].replace("\n", " ")
        print(
            f"Upload failed with HTTP {exc.response.status_code}: {detail}",
        )
        return 1
    except (httpx.HTTPError, OSError, RuntimeError) as exc:
        print(f"Upload failed: {exc}")
        return 1

    print("Demo knowledge loading complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
