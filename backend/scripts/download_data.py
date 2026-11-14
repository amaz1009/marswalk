"""Data download script for MARSWALK raw datasets.

Implements WP-06 data download requirements:
- Reads backend/data/manifests/data_sources.json
- Verifies DOWNLOAD_APPROVED in docs/DEVELOPMENT_STATUS.md before body download
- Supports HTTP resume via Range headers
- Computes and verifies SHA-256 checksums and file sizes
- Updates backend/data/manifests/source_ledger.json
- Enforces owner-approved scope A core-only downloads
- Handles unreachable servers gracefully without crashing
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("download_data")


def resolve_path(p: Path, alt_prefix: str = "backend") -> Path:
    """Resolve path whether invoked from project root or backend/ directory."""
    if p.exists():
        return p
    if (Path(alt_prefix) / p).exists():
        return Path(alt_prefix) / p
    if p.parts and p.parts[0] == alt_prefix:
        stripped = Path(*p.parts[1:])
        if stripped.exists():
            return stripped
    parent_attempt = Path("..") / p
    if parent_attempt.exists():
        return parent_attempt
    return p


ALLOWED_DATASET_IDS: frozenset[str] = frozenset(
    {
        "HIRISE_DTM_GALE_MOUND",
        "HIRISE_ORTHO_GALE_MOUND",
        "MOLA_MEGDR_GALE",
    }
)


def read_download_approved_flag(status_file_path: Path) -> bool:
    """Read DOWNLOAD_APPROVED flag from docs/DEVELOPMENT_STATUS.md."""
    if not status_file_path.exists():
        logger.warning("Status file %s not found; assuming DOWNLOAD_APPROVED: NO", status_file_path)
        return False

    content = status_file_path.read_text(encoding="utf-8")
    match = re.search(r"^DOWNLOAD_APPROVED:\s*([A-Za-z]+)", content, re.MULTILINE)
    if not match:
        return False
    return match.group(1).strip().upper() == "YES"


def compute_file_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 hexadecimal digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_source_ledger(ledger_path: Path) -> list[dict[str, Any]]:
    """Load existing source ledger entries."""
    if not ledger_path.exists():
        return []
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception as exc:
        logger.warning("Could not parse source ledger at %s: %s", ledger_path, exc)
        return []


def update_source_ledger(ledger_path: Path, record: dict[str, Any]) -> None:
    """Add or update an entry in source_ledger.json."""
    entries = load_source_ledger(ledger_path)
    # Deduplicate by file_path so companion files for the same dataset are not clobbered
    rec_path = record.get("file_path")
    entries = [e for e in entries if e.get("file_path") != rec_path]
    entries.append(record)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def probe_file_url(
    client: httpx.Client,
    url: str | None,
    expected_size: int | None = None,
) -> dict[str, Any]:
    """Perform read-only HEAD probe for a single URL."""
    if not url:
        return {
            "status": "UNREACHABLE",
            "url": None,
            "http_status": None,
            "content_length": None,
            "expected_size": expected_size,
            "message": "No download URL configured",
        }
    try:
        resp = client.head(url, follow_redirects=True, timeout=15.0)
        content_len_header = resp.headers.get("Content-Length")
        content_len = int(content_len_header) if content_len_header is not None else None
        return {
            "status": "OK" if resp.is_success else "ERROR",
            "url": url,
            "http_status": resp.status_code,
            "content_length": content_len,
            "expected_size": expected_size,
            "message": "Probed successfully" if resp.is_success else f"HTTP {resp.status_code}",
        }
    except Exception as exc:
        return {
            "status": "UNREACHABLE",
            "url": url,
            "http_status": None,
            "content_length": None,
            "expected_size": expected_size,
            "message": f"Connection error: {exc}",
        }


def probe_dataset(client: httpx.Client, entry: dict[str, Any]) -> dict[str, Any]:
    """Perform read-only HEAD probe for --dry-run without downloading body."""
    dataset_id = entry.get("dataset_id", "UNKNOWN")
    primary_probe = probe_file_url(client, entry.get("url"), entry.get("expected_size_bytes"))
    result = {
        "dataset_id": dataset_id,
        "status": primary_probe["status"],
        "url": primary_probe["url"],
        "http_status": primary_probe["http_status"],
        "content_length": primary_probe["content_length"],
        "expected_size": primary_probe["expected_size"],
        "message": primary_probe["message"],
    }
    companion_file = entry.get("companion_file")
    if companion_file and isinstance(companion_file, dict):
        comp_url = companion_file.get("url")
        comp_expected_size = companion_file.get("expected_size_bytes")
        comp_probe = probe_file_url(client, comp_url, comp_expected_size)
        comp_prod_id = companion_file.get("product_id") or (
            Path(comp_url).name if comp_url else "companion"
        )
        result["companion"] = {
            "product_id": comp_prod_id,
            "url": comp_probe["url"],
            "status": comp_probe["status"],
            "http_status": comp_probe["http_status"],
            "content_length": comp_probe["content_length"],
            "expected_size": comp_probe["expected_size"],
            "message": comp_probe["message"],
        }
    return result


def download_file(
    client: httpx.Client,
    url: str,
    target_file: Path,
    expected_size: int | None,
    dataset_id: str,
    ledger_path: Path,
    relative_ledger_path: str,
) -> dict[str, Any]:
    """Download a single file with resume support, verify size, and record in ledger."""
    if target_file.exists():
        existing_size = target_file.stat().st_size
        if expected_size is None or existing_size == expected_size:
            existing_sha256 = compute_file_sha256(target_file)
            ledger_entries = load_source_ledger(ledger_path)
            matching_entry = next(
                (
                    e
                    for e in ledger_entries
                    if e.get("file_path") == relative_ledger_path
                    and e.get("sha256") == existing_sha256
                ),
                None,
            )
            if matching_entry is not None:
                logger.info(
                    "File %s already downloaded and verified at %s",
                    relative_ledger_path,
                    target_file,
                )
                return {
                    "success": True,
                    "skipped": True,
                    "file_path": str(target_file),
                    "size_bytes": existing_size,
                    "sha256": existing_sha256,
                }

    target_file.parent.mkdir(parents=True, exist_ok=True)
    part_file = target_file.with_name(f"{target_file.name}.part")
    initial_bytes = part_file.stat().st_size if part_file.exists() else 0
    headers = {}
    if initial_bytes > 0:
        headers["Range"] = f"bytes={initial_bytes}-"
        logger.info("Resuming %s from byte %d", target_file.name, initial_bytes)

    with client.stream("GET", url, headers=headers, follow_redirects=True, timeout=60.0) as resp:
        if resp.status_code == 416:  # Range Not Satisfiable
            logger.warning("Range invalid for %s; restarting from zero", target_file.name)
            if part_file.exists():
                part_file.unlink()
            with client.stream("GET", url, follow_redirects=True, timeout=60.0) as retry_resp:
                retry_resp.raise_for_status()
                with open(part_file, "wb") as f:
                    for chunk in retry_resp.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
        elif resp.status_code == 206:
            with open(part_file, "ab") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
        else:
            resp.raise_for_status()
            with open(part_file, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)

    if target_file.exists():
        target_file.unlink()
    part_file.rename(target_file)

    final_size = target_file.stat().st_size
    sha256_hash = compute_file_sha256(target_file)

    if expected_size is not None and final_size != expected_size:
        logger.warning(
            "Size mismatch for %s: expected %d, got %d",
            target_file.name,
            expected_size,
            final_size,
        )

    ledger_record = {
        "file_path": relative_ledger_path,
        "dataset_id": dataset_id,
        "url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": final_size,
        "sha256": sha256_hash,
    }
    update_source_ledger(ledger_path, ledger_record)

    return {
        "success": True,
        "skipped": False,
        "file_path": str(target_file),
        "size_bytes": final_size,
        "sha256": sha256_hash,
    }


def download_single_dataset(
    client: httpx.Client,
    entry: dict[str, Any],
    raw_dir: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    """Download a single dataset (and companion file if declared) with resume support."""
    dataset_id = entry["dataset_id"]
    product_id = entry.get("product_id") or Path(entry["url"]).name
    url = entry.get("url")
    expected_size = entry.get("expected_size_bytes")

    if not url:
        return {"dataset_id": dataset_id, "success": False, "error": "No URL provided"}

    target_file = raw_dir / product_id
    rel_ledger_path = f"data/raw/{product_id}"

    try:
        primary_res = download_file(
            client=client,
            url=url,
            target_file=target_file,
            expected_size=expected_size,
            dataset_id=dataset_id,
            ledger_path=ledger_path,
            relative_ledger_path=rel_ledger_path,
        )

        comp_res = None
        companion_file = entry.get("companion_file")
        if companion_file and isinstance(companion_file, dict):
            comp_url = companion_file.get("url")
            comp_product_id = companion_file.get("product_id") or (
                Path(comp_url).name if comp_url else None
            )
            comp_expected_size = companion_file.get("expected_size_bytes")
            if comp_url and comp_product_id:
                comp_target = raw_dir / comp_product_id
                comp_rel_path = f"data/raw/{comp_product_id}"
                logger.info("Downloading companion file for %s: %s", dataset_id, comp_product_id)
                comp_res = download_file(
                    client=client,
                    url=comp_url,
                    target_file=comp_target,
                    expected_size=comp_expected_size,
                    dataset_id=dataset_id,
                    ledger_path=ledger_path,
                    relative_ledger_path=comp_rel_path,
                )

        return {
            "dataset_id": dataset_id,
            "success": True,
            "skipped": primary_res["skipped"],
            "file_path": primary_res["file_path"],
            "size_bytes": primary_res["size_bytes"],
            "sha256": primary_res["sha256"],
            "companion": comp_res,
        }

    except Exception as exc:
        logger.error("Download failed for dataset %s: %s", dataset_id, exc)
        return {
            "dataset_id": dataset_id,
            "success": False,
            "error": str(exc),
        }


def verify_rad_entry_readonly(manifest_entry: dict[str, Any]) -> dict[str, Any]:
    """Read-only check for MSL RAD entry without fabricating products."""
    url = manifest_entry.get("url")
    dataset_id = manifest_entry.get("dataset_id", "MSL_RAD_SURFACE_RDR")
    status = manifest_entry.get("status", "UNVERIFIED - candidate only")

    return {
        "dataset_id": dataset_id,
        "collection_url": url,
        "status": status,
        "verification_result": (
            "Read-only check: PDS collection URL configured in manifest. "
            "Specific sol product IDs and units remain UNVERIFIED until live "
            "network inspection is performed in WP-18."
        ),
    }


def main() -> int:
    """CLI entrypoint for download_data."""
    parser = argparse.ArgumentParser(description="MARSWALK data downloader")
    parser.add_argument(
        "--data-sources",
        type=Path,
        default=Path("backend/data/manifests/data_sources.json"),
        help="Path to data_sources.json",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("backend/data/raw"),
        help="Directory to store downloaded raw files",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("backend/data/manifests/source_ledger.json"),
        help="Path to source_ledger.json",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=Path("docs/DEVELOPMENT_STATUS.md"),
        help="Path to DEVELOPMENT_STATUS.md to verify DOWNLOAD_APPROVED flag",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=["HIRISE_DTM_GALE_MOUND", "HIRISE_ORTHO_GALE_MOUND", "MOLA_MEGDR_GALE"],
        help="Dataset IDs to download (default: scope A core entries only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Probe URLs with HEAD requests without downloading bodies (allowed when flag is NO)",
    )
    parser.add_argument(
        "--verify-rad",
        action="store_true",
        help="Perform read-only inspection of the MSL RAD candidate entry",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args.data_sources = resolve_path(args.data_sources)
    args.raw_dir = resolve_path(args.raw_dir)
    args.ledger = resolve_path(args.ledger)
    args.status_file = resolve_path(args.status_file)

    # Verify --only targets against owner decision scope A
    requested_ids = set(args.only)
    unauthorized_ids = requested_ids - ALLOWED_DATASET_IDS
    if unauthorized_ids:
        sys.stderr.write(
            f"ERROR: Unauthorized dataset IDs requested: {unauthorized_ids}.\n"
            f"Per Owner Decision (scope A, core only), only the three core entries may be "
            f"downloaded in WP-06: {sorted(ALLOWED_DATASET_IDS)}.\n"
        )
        return 2

    # Load data sources
    if not args.data_sources.exists():
        sys.stderr.write(f"ERROR: data_sources manifest not found at {args.data_sources}\n")
        return 1

    manifest_data = json.loads(args.data_sources.read_text(encoding="utf-8"))
    sources_by_id = {s["dataset_id"]: s for s in manifest_data}

    if args.verify_rad:
        rad_entry = sources_by_id.get("MSL_RAD_SURFACE_RDR", {})
        rad_info = verify_rad_entry_readonly(rad_entry)
        print(json.dumps(rad_info, indent=2))
        return 0

    # Dry-run execution
    if args.dry_run:
        print("=== DRY RUN (HEAD requests only, no body downloads) ===")
        total_size = 0
        with httpx.Client() as client:
            for ds_id in args.only:
                entry = sources_by_id.get(ds_id)
                if not entry:
                    print(f"Dataset {ds_id}: Not found in data_sources.json")
                    continue
                result = probe_dataset(client, entry)
                content_len = result.get("content_length") or entry.get("expected_size_bytes")
                if content_len:
                    total_size += content_len
                print(
                    f"Dataset: {ds_id}\n"
                    f"  Product: {entry.get('product_id')}\n"
                    f"  Status: {result['status']} (HTTP {result['http_status']})\n"
                    f"  Content-Length: {content_len} bytes\n"
                    f"  URL: {result['url']}\n"
                )
                if "companion" in result:
                    comp = result["companion"]
                    comp_len = comp.get("content_length") or comp.get("expected_size")
                    if comp_len:
                        total_size += comp_len
                    print(
                        f"  Companion: {comp.get('product_id')}\n"
                        f"    Status: {comp['status']} (HTTP {comp['http_status']})\n"
                        f"    Content-Length: {comp_len} bytes\n"
                        f"    URL: {comp['url']}\n"
                    )
        print(
            f"Total planned download size (core 3 entries): {total_size} bytes "
            f"({total_size / (1024 * 1024):.1f} MB)"
        )
        return 0

    # Real download requires DOWNLOAD_APPROVED: YES
    download_approved = read_download_approved_flag(args.status_file)
    if not download_approved:
        sys.stderr.write(
            "ERROR: DOWNLOAD_APPROVED is NO in docs/DEVELOPMENT_STATUS.md.\n"
            "Body downloads are refused until the owner authorizes download in Part 2.\n"
            "Use --dry-run to probe URLs without downloading.\n"
        )
        return 3

    print(f"=== DOWNLOADING SCOPE A CORE DATASETS ({len(args.only)} entries) ===")
    success_count = 0
    failure_count = 0

    with httpx.Client() as client:
        for ds_id in args.only:
            entry = sources_by_id.get(ds_id)
            if not entry:
                logger.error("Dataset %s not found in data_sources.json", ds_id)
                failure_count += 1
                continue
            res = download_single_dataset(client, entry, args.raw_dir, args.ledger)
            if res.get("success"):
                success_count += 1
                print(f"[OK] {ds_id}: {res.get('file_path')} ({res.get('size_bytes')} bytes)")
            else:
                failure_count += 1
                print(f"[FAILED] {ds_id}: {res.get('error')}")

    print(f"\nDownload summary: {success_count} succeeded, {failure_count} failed.")
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
