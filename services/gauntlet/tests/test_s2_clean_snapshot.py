"""Clean (unrelated change) revision in snapshot provisioning and registration (offline)."""

import asyncio
import json
from pathlib import Path

import test_b01p_snapshot_bootstrap as b01p
from scripts.prepare_cartwheel_registration import CLEAN_SHA, prepare_registration

from gauntlet.execution.provider_smoke_config import CARTWHEEL_CLEAN_SHA, load_registration

bootstrap = b01p.bootstrap
MANIFEST = json.loads(bootstrap.MANIFEST.read_text())


def _fake_build(repo: Path, sha: str, image: str) -> None:
    (repo / ".next").mkdir(exist_ok=True)
    (repo / ".next/BUILD_ID").write_text(sha)


class CleanClient(b01p.FakeClient):
    async def create(self, params: object, *, timeout: float) -> b01p.FakeSandbox:
        self.params.append(params)
        number = len(self.sandboxes)
        sha = (self.source.base_sha, self.source.head_sha, CLEAN_SHA)[number]
        sandbox = b01p.FakeSandbox(sha, number, None)
        self.sandboxes.append(sandbox)
        return sandbox


def test_clean_pin_is_shared() -> None:
    assert CLEAN_SHA == CARTWHEEL_CLEAN_SHA


def test_clean_revision_rebuilt_verified_and_provisioned(tmp_path: Path) -> None:
    source = bootstrap.prepare_inputs(
        b01p.lockfile(tmp_path),
        bootstrap.VERIFIED_IMAGE,
        build_revision=_fake_build,
        include_clean=True,
    )
    assert source.clean_sha == CLEAN_SHA and source.clean_bundle
    assert [side for side, _, _ in source.revisions()] == ["base", "head", "clean"]
    client = CleanClient(source)
    registration = asyncio.run(
        bootstrap.provision(
            client, source, preview_domain_suffix=".proxy.daytona.work", preview_port=3000
        )
    )
    assert len(client.sandboxes) == 3
    assert all(sandbox.stopped and sandbox.snapshot_name for sandbox in client.sandboxes)
    assert {e["source_sha"] for e in registration["snapshots"]} == {
        source.base_sha,
        source.head_sha,
        CLEAN_SHA,
    }
    assert len(client.deleted) == 3 and len(client.snapshot.deleted) == 1
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(registration))
    change, target = load_registration(path, MANIFEST)
    assert len(target.snapshots) == 3 and change.head_sha == source.head_sha


def test_base_head_only_registration_still_loads(tmp_path: Path) -> None:
    document = prepare_registration(
        base_snapshot="snap-base",
        head_snapshot="snap-head",
        image_digest="0" * 64,
        repo_path="/workspace/cartwheel",
        preview_port=3000,
        preview_domain_suffix=".proxy.daytona.work",
    )
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(document))
    _, target = load_registration(path, MANIFEST)
    assert len(target.snapshots) == 2
