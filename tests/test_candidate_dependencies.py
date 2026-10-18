"""A camada de ferramentas não pode resolver outro conjunto de runtime."""

import json
from importlib import metadata
from pathlib import Path

import pytest


def test_quality_preserves_candidate_runtime_dependencies():
    snapshot = Path("/runtime-dependencies.json")
    if not snapshot.exists():
        pytest.skip("snapshot exclusivo de Dockerfile.verify sobre candidato")
    before = json.loads(snapshot.read_text())
    assert len(before) >= 25
    for name, version in before.items():
        assert metadata.version(name) == version, name
