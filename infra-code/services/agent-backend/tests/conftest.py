"""Shared fixtures. Every required secret is set here so Settings validates."""

from __future__ import annotations

import os

import pytest

_ENV = {
    "JWT_SECRET": "unit-test-secret",
    "JWT_ISS": "mvp-app",
    "POSTGRES_USER": "agent",
    "POSTGRES_PASSWORD": "unit-test-pw",
    "POSTGRES_DB": "agentmvp",
    "GOOGLE_API_KEY": "unit-test-key",
    "KAGENT_AGENT_A2A_URL": "http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent",
    "MINIO_ROOT_USER": "unit",
    "MINIO_ROOT_PASSWORD": "unit-pw",
}

for _k, _v in _ENV.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture
def settings():
    """A validated Settings instance."""
    from app.config import Settings

    return Settings()
