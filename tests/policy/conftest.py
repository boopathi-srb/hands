from __future__ import annotations

import pytest
from policy_helpers import COREONE_POLICY_PATH, config_from, minimal_policy_mapping

from hands.policy import PolicyConfig, YamlPolicyGate, load_policy


@pytest.fixture
def coreone_config() -> PolicyConfig:
    result = load_policy(COREONE_POLICY_PATH)
    assert result.ok, getattr(result, "message", "")
    return result.config


@pytest.fixture
def coreone_gate(coreone_config: PolicyConfig) -> YamlPolicyGate:
    return YamlPolicyGate(coreone_config)


@pytest.fixture
def minimal_gate() -> YamlPolicyGate:
    return YamlPolicyGate(config_from(minimal_policy_mapping()))
