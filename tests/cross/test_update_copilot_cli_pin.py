from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory


SPEC = spec_from_file_location(
    "update_copilot_cli_pin",
    Path(__file__).resolve().parents[2] / ".github/scripts/update_copilot_cli_pin.py",
)
assert SPEC and SPEC.loader
updater = module_from_spec(SPEC)
SPEC.loader.exec_module(updater)

NOW = datetime(2026, 11, 17, tzinfo=UTC)
WINDOWS_SHA = "a" * 64
LINUX_X64_SHA = "b" * 64
LINUX_ARM64_SHA = "c" * 64
LICENSE_BYTES = b"Copilot CLI license"


def _release(version: str, published: str, **flags: object) -> dict:
    assets = []
    for name, digest in (
        ("copilot-linux-x64.tar.gz", "b" * 64),
        ("copilot-linux-arm64.tar.gz", "c" * 64),
        ("copilot-win32-x64.zip", WINDOWS_SHA),
    ):
        assets.append(
            {
                "name": name,
                "digest": f"sha256:{digest}",
                "browser_download_url": (
                    "https://github.com/github/copilot-cli/releases/download/"
                    f"v{version}/{name}"
                ),
            }
        )
    return {
        "tag_name": f"v{version}",
        "published_at": published,
        "draft": False,
        "prerelease": False,
        "assets": assets,
        **flags,
    }


def _npm_metadata() -> dict:
    return {
        "versions": {
            "1.0.109": {},
            "1.0.110": {},
            "1.0.111": {},
        },
        "time": {
            "1.0.109": "2026-11-01T00:00:00Z",
            "1.0.110": "2026-11-09T00:00:00Z",
            "1.0.111": "2026-11-16T00:00:00Z",
        },
    }


def _files(directory: str) -> tuple[Path, Path, Path, Path]:
    root = Path(directory)
    catalog = root / "catalog.py"
    linux_dockerfile = root / "Dockerfile"
    dockerfile = root / "Dockerfile.windows"
    registry = root / "acp-providers.json"
    catalog.write_text('COPILOT_CLI_VERSION = "1.0.109"\n', encoding="utf-8")
    linux_dockerfile.write_text(
        "\n".join(
            (
                "ARG COPILOT_CLI_VERSION=1.0.109",
                f"ARG COPILOT_CLI_LINUX_X64_SHA256={'f' * 64}",
                f"ARG COPILOT_CLI_LINUX_ARM64_SHA256={'f' * 64}",
                f"ARG COPILOT_CLI_LICENSE_SHA256={'e' * 64}",
                "",
            )
        ),
        encoding="utf-8",
    )
    dockerfile.write_text(
        "\n".join(
            (
                "ARG COPILOT_CLI_VERSION=1.0.109",
                "ARG COPILOT_CLI_URL=https://example.test/v1.0.109/copilot.zip",
                f"ARG COPILOT_CLI_SHA256={'d' * 64}",
                "ARG COPILOT_CLI_LICENSE_URL=https://example.test/v1.0.109/LICENSE.md",
                f"ARG COPILOT_CLI_LICENSE_SHA256={'e' * 64}",
                "",
            )
        ),
        encoding="utf-8",
    )
    registry.write_text(
        '{"default_command":["@github/copilot@1.0.109"]}\n',
        encoding="utf-8",
    )
    return catalog, linux_dockerfile, dockerfile, registry


def test_updates_catalog_image_assets_license_and_typescript_registry() -> None:
    releases = [
        _release("1.0.110", "2026-11-09T00:00:00Z"),
        _release("1.0.111", "2026-11-16T00:00:00Z"),
    ]
    with TemporaryDirectory() as directory:
        catalog, linux_dockerfile, dockerfile, registry = _files(directory)
        selected = updater.update_pins(
            catalog,
            linux_dockerfile,
            dockerfile,
            registry,
            releases,
            _npm_metadata(),
            NOW,
            lambda _: LICENSE_BYTES,
        )

        assert selected == "1.0.110"
        assert 'COPILOT_CLI_VERSION = "1.0.110"' in catalog.read_text()
        linux_text = linux_dockerfile.read_text()
        assert "ARG COPILOT_CLI_VERSION=1.0.110" in linux_text
        assert f"ARG COPILOT_CLI_LINUX_X64_SHA256={LINUX_X64_SHA}" in linux_text
        assert (
            f"ARG COPILOT_CLI_LINUX_ARM64_SHA256={LINUX_ARM64_SHA}" in linux_text
        )
        assert updater.hashlib.sha256(LICENSE_BYTES).hexdigest() in linux_text
        docker_text = dockerfile.read_text()
        assert "ARG COPILOT_CLI_VERSION=1.0.110" in docker_text
        assert f"ARG COPILOT_CLI_SHA256={WINDOWS_SHA}" in docker_text
        assert updater.hashlib.sha256(LICENSE_BYTES).hexdigest() in docker_text
        assert "@github/copilot@1.0.110" in registry.read_text()


def test_requires_both_github_and_npm_to_complete_observation_period() -> None:
    releases = [_release("1.0.110", "2026-11-01T00:00:00Z")]
    metadata = _npm_metadata()
    metadata["time"]["1.0.110"] = "2026-11-16T00:00:00Z"
    with TemporaryDirectory() as directory:
        catalog, linux_dockerfile, dockerfile, registry = _files(directory)
        assert (
            updater.update_pins(
                catalog,
                linux_dockerfile,
                dockerfile,
                registry,
                releases,
                metadata,
                NOW,
                lambda _: LICENSE_BYTES,
            )
            == "1.0.109"
        )
        assert 'COPILOT_CLI_VERSION = "1.0.109"' in catalog.read_text()


def test_missing_required_release_asset_fails_before_writing() -> None:
    release = _release("1.0.110", "2026-11-01T00:00:00Z")
    release["assets"] = release["assets"][:-1]
    with TemporaryDirectory() as directory:
        catalog, linux_dockerfile, dockerfile, registry = _files(directory)
        before = (
            catalog.read_text(),
            linux_dockerfile.read_text(),
            dockerfile.read_text(),
            registry.read_text(),
        )
        try:
            updater.update_pins(
                catalog,
                linux_dockerfile,
                dockerfile,
                registry,
                [release],
                _npm_metadata(),
                NOW,
                lambda _: LICENSE_BYTES,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("release with a missing Windows asset was accepted")
        assert before == (
            catalog.read_text(),
            linux_dockerfile.read_text(),
            dockerfile.read_text(),
            registry.read_text(),
        )
