from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import numpy as np
import pytest

from backend.components.catalog import DINOV3_COMPONENT
from backend.components.manager import ComponentManager, _safe_extract
from backend.components.protocol import EmbeddingProviderClient
from tests.tool_test_utils import RecordingContext


def test_component_state_requires_matching_license_digest(tmp_path: Path) -> None:
    manager = ComponentManager(tmp_path / "components", tmp_path / "models")

    pending = manager.public_state(DINOV3_COMPONENT, None)
    stale = manager.public_state(
        DINOV3_COMPONENT,
        {"accepted": True, "license_sha256": "0" * 64},
    )
    accepted = manager.public_state(
        DINOV3_COMPONENT,
        {"accepted": True, "license_sha256": DINOV3_COMPONENT.license.sha256},
    )

    assert pending["license_accepted"] is False
    assert stale["license_accepted"] is False
    assert accepted["license_accepted"] is True


def test_component_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "component.tar.gz"
    with tarfile.open(archive, "w:gz") as package:
        payload = b"bad"
        member = tarfile.TarInfo("../escape")
        member.size = len(payload)
        package.addfile(member, io.BytesIO(payload))

    with pytest.raises(RuntimeError, match="不安全路径"):
        _safe_extract(archive, tmp_path / "target")


def test_provider_protocol_handshake_and_embedding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "fake_provider.py"
    provider.write_text(
        """
import json, sys
def emit(value):
    print(json.dumps(value), flush=True)
emit({"event":"ready","protocol_version":1,"provider_id":"dinov3-cpu",\
"provider_version":"0.1.0","model_id":"fake","model_revision":"1",\
"model_dir":"/tmp/models","devices":["cpu"]})
for line in sys.stdin:
    request = json.loads(line)
    if request["method"] == "shutdown":
        break
    items = [{"path": path, "embedding": [1.0, 0.0]} for path in request["paths"]]
    emit({"event":"batch","batch_size":request["batch_size"],"items":items})
    emit({"event":"complete","batch_size":request["batch_size"],"device":"cpu"})
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "TOOLBOX_DINOV3_PROVIDER_COMMAND",
        f"{sys.executable} {provider}",
    )
    manager = ComponentManager(tmp_path / "components", tmp_path / "models")
    context = RecordingContext(tmp_path / "output")
    paths = [tmp_path / "one.jpg", tmp_path / "two.jpg"]

    with EmbeddingProviderClient(manager, "dinov3-cpu", context) as client:
        result = client.embed(paths, batch_size=2, device="auto")

    assert result.metadata.provider_id == "dinov3-cpu"
    assert result.device == "cpu"
    assert result.errors == {}
    assert np.array_equal(result.embeddings[paths[0]], np.array([1.0, 0.0], dtype=np.float32))


def test_provider_rejects_unsupported_cuda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "fake_provider.py"
    provider.write_text(
        """
import json, sys
print(json.dumps({"event":"ready","protocol_version":1,"provider_id":"dinov3-cpu",\
"provider_version":"0.1.0","model_id":"fake","model_revision":"1",\
"model_dir":"/tmp/models","devices":["cpu"]}), flush=True)
for line in sys.stdin:
    if json.loads(line)["method"] == "shutdown": break
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "TOOLBOX_DINOV3_PROVIDER_COMMAND",
        f"{sys.executable} {provider}",
    )
    manager = ComponentManager(tmp_path / "components", tmp_path / "models")
    with EmbeddingProviderClient(
        manager,
        "dinov3-cpu",
        RecordingContext(tmp_path / "output"),
    ) as client:
        with pytest.raises(RuntimeError, match="不支持 CUDA"):
            client.embed([tmp_path / "one.jpg"], batch_size=1, device="cuda")
