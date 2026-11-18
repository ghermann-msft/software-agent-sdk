"""Named, reference-bearing agent launch specs (``AgentProfile``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from openhands.sdk.profiles.agent_profile import (
    AGENT_PROFILE_SCHEMA_VERSION,
    ACPAgentProfile,
    AgentProfile,
    AgentProfileBase,
    AgentProfileInfo,
    AgentProfileListResponse,
    LaunchedAgentProfile,
    OpenHandsAgentProfile,
    ProfileVerificationSettings,
    build_profile_verification,
    safe_validation_error_detail,
    validate_agent_profile,
)
from openhands.sdk.profiles.agent_profile_store import (
    AgentProfileStore,
    AgentProfileStoreProtocol,
    ProfileLimitExceeded,
    save_profile_preserving_identity,
)
from openhands.sdk.profiles.profile_refs import (
    ProfileReferenced,
    cascade_rename,
    delete_llm_profile,
    find_referrers,
    rename_llm_profile,
)
from openhands.sdk.profiles.resolver import (
    AgentProfileDiagnostics,
    ProfileNotFound,
)
from openhands.sdk.profiles.seed import (
    SEED_PROFILE_NAME,
    build_seed_profile,
)
from openhands.sdk.settings.model import OpenHandsAgentSettings
from openhands.sdk.tool.defaults import launch_tool_specs

if TYPE_CHECKING:
    from collections.abc import Collection

    from pydantic import SecretStr

    from openhands.sdk.llm.llm_profile_store import LLMProfileLoader
    from openhands.sdk.mcp.config import MCPServer
    from openhands.sdk.settings.model import AgentSettingsConfig
    from openhands.sdk.skills import Skill
    from openhands.sdk.utils.cipher import Cipher


def resolve_agent_profile(
    profile: OpenHandsAgentProfile | ACPAgentProfile,
    *,
    llm_store: LLMProfileLoader,
    mcp_config: dict[str, MCPServer],
    available_skills: list[Skill] | None,
    public_skill_names: Collection[str] | None = None,
    critic_api_key: SecretStr | None = None,
    cipher: Cipher | None = None,
    browser_available: bool | None = None,
) -> AgentSettingsConfig:
    """Resolve an Agent Profile through the canonical launch pipeline."""
    # launch.resolve imports profile helpers, so importing it eagerly would cycle.
    from openhands.sdk.launch import LaunchStores, resolve

    resolved = resolve(
        profile,
        LaunchStores(
            llm_profiles=llm_store,
            mcp_config=mcp_config,
            skills=lambda: list(available_skills or []),
            public_skill_names=(
                None
                if public_skill_names is None
                else lambda: list(public_skill_names)
            ),
            critic_api_key=critic_api_key,
            cipher=cipher,
        ),
    )
    settings = resolved.settings
    if isinstance(settings, OpenHandsAgentSettings) and browser_available is not None:
        settings = settings.model_copy(
            update={
                "tools": launch_tool_specs(
                    settings.tools,
                    browser_available=browser_available,
                )
            }
        )
    return settings


__all__ = [
    "AGENT_PROFILE_SCHEMA_VERSION",
    "ACPAgentProfile",
    "AgentProfile",
    "AgentProfileBase",
    "AgentProfileInfo",
    "AgentProfileListResponse",
    "AgentProfileDiagnostics",
    "AgentProfileStore",
    "AgentProfileStoreProtocol",
    "LaunchedAgentProfile",
    "OpenHandsAgentProfile",
    "ProfileLimitExceeded",
    "ProfileNotFound",
    "ProfileReferenced",
    "ProfileVerificationSettings",
    "SEED_PROFILE_NAME",
    "build_profile_verification",
    "build_seed_profile",
    "cascade_rename",
    "delete_llm_profile",
    "find_referrers",
    "rename_llm_profile",
    "resolve_agent_profile",
    "safe_validation_error_detail",
    "save_profile_preserving_identity",
    "validate_agent_profile",
]
