"""Shared, provider-independent execution resource management."""

from .environment_pair import GateEnvironmentPair, gate_environment_pair

__all__ = ["GateEnvironmentPair", "gate_environment_pair"]
