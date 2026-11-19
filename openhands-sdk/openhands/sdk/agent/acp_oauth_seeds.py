"""Process-local private storage for ACP OAuth bridge seeds."""

from __future__ import annotations

import atexit
import ctypes
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path


_SERVER_ROOT_PREFIX = "openhands-agent-server-"
_OAUTH_SEED_SUBDIR = "acp-oauth"
_STALE_AFTER_SECONDS = 24 * 60 * 60
_PROCESS_ROOT = Path(tempfile.gettempdir()) / f"{_SERVER_ROOT_PREFIX}{os.getpid()}"
_OAUTH_SEED_ROOT = _PROCESS_ROOT / _OAUTH_SEED_SUBDIR
_cleanup_registered = False


def _server_root_pid(server_root: Path) -> int | None:
    suffix = server_root.name.removeprefix(_SERVER_ROOT_PREFIX)
    try:
        return int(suffix)
    except ValueError:
        return None


def _process_is_running(pid: int) -> bool:
    if os.name == "nt":
        process_query_limited_information = 0x1000
        kernel32 = ctypes.CDLL("kernel32.dll", use_last_error=True)
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_stale_acp_oauth_seed_roots(
    *,
    now: float | None = None,
) -> None:
    cutoff = (time.time() if now is None else now) - _STALE_AFTER_SECONDS
    temp_root = Path(tempfile.gettempdir())
    for server_root in temp_root.glob(f"{_SERVER_ROOT_PREFIX}*"):
        if server_root == _PROCESS_ROOT:
            continue
        pid = _server_root_pid(server_root)
        if pid is None or _process_is_running(pid):
            continue
        seed_root = server_root / _OAUTH_SEED_SUBDIR
        try:
            if seed_root.stat().st_mtime > cutoff:
                continue
            shutil.rmtree(seed_root)
            server_root.rmdir()
        except FileNotFoundError:
            continue
        except OSError:
            continue


def _cleanup_process_seed_root() -> None:
    shutil.rmtree(_OAUTH_SEED_ROOT, ignore_errors=True)
    try:
        _PROCESS_ROOT.rmdir()
    except OSError:
        pass


def get_acp_oauth_seed_dir(conversation_id: str) -> Path:
    global _cleanup_registered

    _PROCESS_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    _PROCESS_ROOT.chmod(0o700)
    _OAUTH_SEED_ROOT.mkdir(mode=0o700, exist_ok=True)
    _OAUTH_SEED_ROOT.chmod(0o700)
    conversation_key = hashlib.sha256(conversation_id.encode()).hexdigest()[:24]
    conversation_root = _OAUTH_SEED_ROOT / conversation_key
    conversation_root.mkdir(mode=0o700, exist_ok=True)
    conversation_root.chmod(0o700)
    if not _cleanup_registered:
        atexit.register(_cleanup_process_seed_root)
        _cleanup_registered = True
    return conversation_root
