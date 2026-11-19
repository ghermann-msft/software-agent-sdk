import os
import time

import pytest

from openhands.sdk.agent import acp_oauth_seeds


@pytest.fixture
def private_seed_root(tmp_path, monkeypatch):
    process_root = tmp_path / f"openhands-agent-server-{os.getpid()}"
    seed_root = process_root / "acp-oauth"
    monkeypatch.setattr(acp_oauth_seeds, "_PROCESS_ROOT", process_root)
    monkeypatch.setattr(acp_oauth_seeds, "_OAUTH_SEED_ROOT", seed_root)
    monkeypatch.setattr(acp_oauth_seeds, "_cleanup_registered", False)
    return process_root, seed_root


def test_get_acp_oauth_seed_dir_creates_private_process_local_directory(
    private_seed_root,
):
    process_root, seed_root = private_seed_root

    conversation_root = acp_oauth_seeds.get_acp_oauth_seed_dir(
        "conversation/with/unsafe/path"
    )

    assert conversation_root.parent == seed_root
    assert conversation_root.name != "conversation/with/unsafe/path"
    if os.name != "nt":
        assert process_root.stat().st_mode & 0o777 == 0o700
        assert seed_root.stat().st_mode & 0o777 == 0o700
        assert conversation_root.stat().st_mode & 0o777 == 0o700


def test_cleanup_stale_acp_oauth_seed_roots_removes_only_old_seed_data(
    tmp_path, monkeypatch
):
    current_root = tmp_path / f"openhands-agent-server-{os.getpid()}"
    old_root = tmp_path / "openhands-agent-server-123"
    recent_root = tmp_path / "openhands-agent-server-456"
    active_root = tmp_path / "openhands-agent-server-789"
    for root in (current_root, old_root, recent_root, active_root):
        seed_root = root / "acp-oauth"
        seed_root.mkdir(parents=True)
        (seed_root / "seed.json").write_text("secret")
    now = time.time()
    os.utime(old_root / "acp-oauth", (now - 90_000, now - 90_000))
    os.utime(active_root / "acp-oauth", (now - 90_000, now - 90_000))
    monkeypatch.setattr(acp_oauth_seeds.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(acp_oauth_seeds, "_PROCESS_ROOT", current_root)
    monkeypatch.setattr(
        acp_oauth_seeds,
        "_process_is_running",
        lambda pid: pid == 789,
    )

    acp_oauth_seeds.cleanup_stale_acp_oauth_seed_roots(now=now)

    assert current_root.exists()
    assert not old_root.exists()
    assert recent_root.exists()
    assert active_root.exists()
