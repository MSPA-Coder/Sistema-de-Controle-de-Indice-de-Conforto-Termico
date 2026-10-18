"""Conferência da resolução efetiva, não só das declarações no arquivo."""

import json
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def test_installed_packages_obey_constraints():
    root = Path(__file__).resolve().parents[1]
    installed = {
        canonicalize_name(dist.metadata["Name"]): dist.version for dist in metadata.distributions()
    }
    checked = 0
    for line in (root / "constraints.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        if name in installed:
            assert installed[name] in requirement.specifier, name
            checked += 1
    assert checked >= 30  # runtime + ferramentas, não apenas um pacote avulso


def test_sharedauth_installed_commit_is_the_declared_immutable_revision():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    requirement = next(
        Requirement(r) for r in project["dependencies"] if r.startswith("sharedauth[")
    )
    revision = requirement.url.rsplit("@", 1)[1]
    assert len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)
    provenance = json.loads(metadata.distribution("sharedauth").read_text("direct_url.json"))
    assert provenance["vcs_info"]["commit_id"] == revision
    assert provenance["url"] == "https://github.com/MSPA-Coder/SharedAuth.git"
