#!/usr/bin/env python3
"""Update the Copilot CLI image pins after a seven-day observation window."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path


RELEASES_URL = "https://api.github.com/repos/github/copilot-cli/releases?per_page=100"
NPM_METADATA_URL = "https://registry.npmjs.org/@github%2Fcopilot"
OBSERVATION_PERIOD = timedelta(days=7)
VERSION = re.compile(r"\d+\.\d+\.\d+")
CATALOG_VERSION = re.compile(r'(?m)^COPILOT_CLI_VERSION = "(\d+\.\d+\.\d+)"$')
DOCKER_VERSION = re.compile(r"(?m)^ARG COPILOT_CLI_VERSION=(\d+\.\d+\.\d+)$")
DOCKER_URL = re.compile(r"(?m)^ARG COPILOT_CLI_URL=(\S+)$")
DOCKER_SHA256 = re.compile(r"(?m)^ARG COPILOT_CLI_SHA256=([0-9a-f]{64})$")
DOCKER_LICENSE_URL = re.compile(r"(?m)^ARG COPILOT_CLI_LICENSE_URL=(\S+)$")
DOCKER_LICENSE_SHA256 = re.compile(
    r"(?m)^ARG COPILOT_CLI_LICENSE_SHA256=([0-9a-f]{64})$"
)
TS_PACKAGE = re.compile(r"@github/copilot@(\d+\.\d+\.\d+)")
REQUIRED_ASSETS = (
    "copilot-linux-x64.tar.gz",
    "copilot-linux-arm64.tar.gz",
    "copilot-win32-x64.zip",
)


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def _published_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def select_release(
    releases: list[dict],
    npm_metadata: dict,
    current: str,
    now: datetime,
) -> dict | None:
    """Return the newest release observed on GitHub and npm, or ``None``."""
    cutoff = now - OBSERVATION_PERIOD
    current_parts = _version_tuple(current)
    npm_versions = npm_metadata.get("versions", {})
    npm_times = npm_metadata.get("time", {})
    best: tuple[tuple[int, int, int], dict] | None = None
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        version = str(release.get("tag_name") or "").removeprefix("v")
        if not VERSION.fullmatch(version):
            continue
        parts = _version_tuple(version)
        if parts <= current_parts:
            continue
        if _published_at(str(release["published_at"])) > cutoff:
            continue
        npm_release = npm_versions.get(version)
        npm_time = npm_times.get(version)
        if not isinstance(npm_release, dict) or not isinstance(npm_time, str):
            continue
        if npm_release.get("deprecated") or _published_at(npm_time) > cutoff:
            continue
        if best is None or parts > best[0]:
            best = (parts, release)
    return best[1] if best is not None else None


def _release_assets(release: dict) -> dict[str, dict]:
    assets = {asset.get("name"): asset for asset in release.get("assets", [])}
    missing = [name for name in REQUIRED_ASSETS if name not in assets]
    if missing:
        raise ValueError(f"Copilot CLI release is missing assets: {', '.join(missing)}")
    for name in REQUIRED_ASSETS:
        digest = str(assets[name].get("digest") or "")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ValueError(f"Copilot CLI asset {name} has no sha256 digest")
        if not assets[name].get("browser_download_url"):
            raise ValueError(f"Copilot CLI asset {name} has no download URL")
    return assets


def _replace_once(pattern: re.Pattern[str], replacement: str, text: str) -> str:
    updated, count = pattern.subn(replacement, text)
    if count != 1:
        raise ValueError(f"expected exactly one pin matching {pattern.pattern!r}")
    return updated


def update_pins(
    catalog: Path,
    windows_dockerfile: Path,
    typescript_registry: Path,
    releases: list[dict],
    npm_metadata: dict,
    now: datetime,
    fetch_bytes: Callable[[str], bytes],
) -> str:
    catalog_text = catalog.read_text(encoding="utf-8")
    matches = CATALOG_VERSION.findall(catalog_text)
    if len(matches) != 1:
        raise ValueError("expected exactly one COPILOT_CLI_VERSION catalog pin")
    current = matches[0]
    selected = select_release(releases, npm_metadata, current, now)
    if selected is None:
        return current

    selected_version = str(selected["tag_name"]).removeprefix("v")
    assets = _release_assets(selected)
    windows_asset = assets["copilot-win32-x64.zip"]
    windows_url = str(windows_asset["browser_download_url"])
    windows_sha256 = str(windows_asset["digest"]).removeprefix("sha256:")
    license_url = (
        "https://raw.githubusercontent.com/github/copilot-cli/"
        f"v{selected_version}/LICENSE.md"
    )
    license_sha256 = hashlib.sha256(fetch_bytes(license_url)).hexdigest()

    docker_text = windows_dockerfile.read_text(encoding="utf-8")
    registry_text = typescript_registry.read_text(encoding="utf-8")
    updated_catalog = _replace_once(
        CATALOG_VERSION,
        f'COPILOT_CLI_VERSION = "{selected_version}"',
        catalog_text,
    )
    updated_docker = _replace_once(
        DOCKER_VERSION,
        f"ARG COPILOT_CLI_VERSION={selected_version}",
        docker_text,
    )
    updated_docker = _replace_once(
        DOCKER_URL, f"ARG COPILOT_CLI_URL={windows_url}", updated_docker
    )
    updated_docker = _replace_once(
        DOCKER_SHA256,
        f"ARG COPILOT_CLI_SHA256={windows_sha256}",
        updated_docker,
    )
    updated_docker = _replace_once(
        DOCKER_LICENSE_URL,
        f"ARG COPILOT_CLI_LICENSE_URL={license_url}",
        updated_docker,
    )
    updated_docker = _replace_once(
        DOCKER_LICENSE_SHA256,
        f"ARG COPILOT_CLI_LICENSE_SHA256={license_sha256}",
        updated_docker,
    )
    updated_registry = _replace_once(
        TS_PACKAGE,
        f"@github/copilot@{selected_version}",
        registry_text,
    )

    catalog.write_text(updated_catalog, encoding="utf-8")
    windows_dockerfile.write_text(updated_docker, encoding="utf-8")
    typescript_registry.write_text(updated_registry, encoding="utf-8")
    return selected_version


def _fetch_json(url: str) -> dict | list[dict]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--windows-dockerfile", type=Path, required=True)
    parser.add_argument("--typescript-registry", type=Path, required=True)
    args = parser.parse_args()
    releases = _fetch_json(RELEASES_URL)
    npm_metadata = _fetch_json(NPM_METADATA_URL)
    if not isinstance(releases, list) or not isinstance(npm_metadata, dict):
        raise ValueError("unexpected Copilot CLI release metadata shape")
    print(
        update_pins(
            args.catalog,
            args.windows_dockerfile,
            args.typescript_registry,
            releases,
            npm_metadata,
            datetime.now(UTC),
            _fetch_bytes,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
