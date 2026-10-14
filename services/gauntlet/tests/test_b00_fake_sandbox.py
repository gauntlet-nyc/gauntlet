import pytest

from gauntlet.integrations.fake.sandbox import FakeSandboxProvider, Fixture
from gauntlet.ports.errors import EnvironmentUnavailableError


@pytest.mark.asyncio
async def test_sandbox_rejects_unregistered_target_before_creating_environment() -> None:
    provider = FakeSandboxProvider(
        fixtures={
            "cartwheel-fixture": Fixture(
                fixture_id="baseline-v1",
                checksum="0" * 64,
                allowed_shas=frozenset({"aaaaaaaa"}),
            )
        }
    )

    with pytest.raises(EnvironmentUnavailableError):
        await provider.create(
            target_id="unregistered-target",
            source_sha="aaaaaaaa",
            fixture_id="baseline-v1",
            mode="gate_compare",
        )
