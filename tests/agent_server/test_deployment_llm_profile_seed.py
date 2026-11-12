from unittest.mock import patch

from openhands.agent_server.agent_profiles_router import (
    _ensure_active_profile,
    _ensure_default_llm_profile,
)
from openhands.agent_server.config import Config
from openhands.agent_server.persistence import FileSettingsStore, PersistedSettings
from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.profiles import AgentProfileStore, OpenHandsAgentProfile


def _set_azure_llm_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "azure/gpt-5.6-sol")
    monkeypatch.setenv(
        "LLM_BASE_URL",
        "https://mortmain-openai2.openai.azure.com",
    )
    monkeypatch.setenv("LLM_API_VERSION", "2024-12-01-preview")
    monkeypatch.setenv("LLM_AUTH_TYPE", "azure_workload_identity")


def test_ensure_default_llm_profile_repairs_unconfigured_settings(
    monkeypatch, tmp_path
) -> None:
    settings_store = FileSettingsStore(tmp_path / "settings")
    settings_store.save(PersistedSettings())
    llm_store = LLMProfileStore(base_dir=tmp_path / "profiles")
    _set_azure_llm_env(monkeypatch)

    with patch(
        "openhands.agent_server.agent_profiles_router.get_llm_profile_store",
        return_value=llm_store,
    ):
        settings = _ensure_default_llm_profile(settings_store, cipher=None)

    assert settings.active_profile == "default"
    llm = llm_store.load("default")
    assert llm.model == "azure/gpt-5.6-sol"
    assert llm.auth_type == "azure_workload_identity"


def test_ensure_default_llm_profile_preserves_active_user_profile(
    monkeypatch, tmp_path
) -> None:
    settings_store = FileSettingsStore(tmp_path / "settings")
    settings = PersistedSettings(active_profile="mine")
    settings_store.save(settings)
    llm_store = LLMProfileStore(base_dir=tmp_path / "profiles")
    llm_store.save("mine", LLM(model="anthropic/claude-sonnet-4-5"))
    _set_azure_llm_env(monkeypatch)

    with patch(
        "openhands.agent_server.agent_profiles_router.get_llm_profile_store",
        return_value=llm_store,
    ):
        loaded = _ensure_default_llm_profile(settings_store, cipher=None)

    assert loaded.active_profile == "mine"
    assert llm_store.list() == ["mine.json"]


def test_active_agent_profile_repairs_dangling_default_llm_ref(
    monkeypatch, tmp_path
) -> None:
    settings_store = FileSettingsStore(tmp_path / "settings")
    agent_store = AgentProfileStore(base_dir=tmp_path / "agent-profiles")
    agent_profile = OpenHandsAgentProfile(name="default", llm_profile_ref="default")
    agent_store.save(agent_profile)
    settings_store.save(
        PersistedSettings(active_agent_profile_id=str(agent_profile.id))
    )
    llm_store = LLMProfileStore(base_dir=tmp_path / "profiles")
    _set_azure_llm_env(monkeypatch)

    with (
        patch(
            "openhands.agent_server.agent_profiles_router.get_settings_store",
            return_value=settings_store,
        ),
        patch(
            "openhands.agent_server.agent_profiles_router.get_llm_profile_store",
            return_value=llm_store,
        ),
    ):
        _ensure_active_profile(
            agent_store,
            Config(static_files_path=None, session_api_keys=[], secret_key=None),
            cipher=None,
        )

    settings = settings_store.load()
    assert settings is not None
    assert settings.active_agent_profile_id == str(agent_profile.id)
    assert settings.active_profile == "default"
    assert llm_store.load("default").model == "azure/gpt-5.6-sol"
