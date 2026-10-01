"""Resolve trusted named profiles; credentials never become wire configuration."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

from ebd.contracts import EngineError
from ebd.providers import ProviderConfig


def local_profiles(workspace, env_file=None):
    """Load opt-in host configuration; never accept endpoints from browser input."""
    path = Path(env_file or Path(workspace) / "local" / ".env")
    values = {str(k).upper(): v for k, v in dotenv_values(path).items() if v}
    values.update({k.upper(): v for k, v in os.environ.items()})
    base = values.get("NINFER_BASE_URL")
    if not base:
        return {}
    model = values.get("NINFER_MODEL", "qwen38-ninfer-256k")
    config = ProviderConfig("ninfer", model, base,
        settings={"max_tokens": 4096, "temperature": 0.2},
        profile_name="ninfer", endpoint_id="local-ninfer")
    from ebd.providers.factory import _validate_config
    _validate_config(config)
    return {"ninfer": config}


class ProfileRegistry:
    def __init__(self, settings):
        self.settings = settings
        workspace = Path(settings.workspace).resolve()
        self.env_path = Path(settings.env_file or workspace / "local" / ".env")

    def resolve(self, definition):
        if definition.profile_ref in self.settings.profiles:
            config = self.settings.profiles[definition.profile_ref]
            if not isinstance(config, ProviderConfig):
                raise EngineError("INVALID_DATA", "Trusted profile must be a ProviderConfig")
            if config.model_id != definition.model_ref:
                raise EngineError("PROFILE_MISMATCH", "Definition model differs from the pinned profile")
            return config
        # Only a trusted local file and process environment supply credentials.
        values = {str(k).upper(): v for k, v in dotenv_values(self.env_path).items() if v}
        values.update({k.upper(): v for k, v in os.environ.items()})
        if definition.profile_ref == "deepseek" and definition.model_ref == "deepseek-flash":
            provider, base, key = "deepseek", "https://api.deepseek.com", values.get("DEEPSEEK_API_KEY", "")
            settings = {"thinking": "disabled"}
        elif definition.profile_ref == "openai" and definition.model_ref == "gpt-6-luna":
            provider, base, key = "openai", "https://api.openai.com/v1", values.get("OPENAI_API_KEY", "")
            settings = {"reasoning_effort": "low"}
        else:
            raise EngineError("PROFILE_NOT_FOUND", "Register an explicit trusted profile for this model")
        if not key:
            raise EngineError("CREDENTIAL_MISSING", "The selected API credential is not configured", {"provider": provider})
        settings.update(definition.settings)
        return ProviderConfig(provider, definition.model_ref, base, key, settings,
                              profile_name=definition.profile_ref, endpoint_id=provider + "-official")
