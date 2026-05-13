from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .audit import audit_expected_files, generate_audit
from .compile import compile_author, compile_source, default_source_path, write_compiled
from .io import write_json, write_yaml
from .layers import parse_layers
from .paths import COMPILED_CONTRACT_PATH
from .project import projection_files
from .validate import validate_project as _validate_project


@dataclass(frozen=True)
class ArtifactPolicy:
    """Controls which generated artifacts are treated as durable outputs."""

    include_audit_pngs: bool = True

    def filter(self, paths: Iterable[str]) -> set[str]:
        if self.include_audit_pngs:
            return set(paths)
        return {path for path in paths if not path.endswith(".png")}


@dataclass(frozen=True)
class ProjectConfig:
    root: Path = Path(".")
    source: Path | None = None
    layers: set[str] | None = None
    artifact_policy: ArtifactPolicy = ArtifactPolicy()
    render_audit: bool = True


def _coerce_layers(layers: str | set[str] | None) -> set[str] | None:
    if isinstance(layers, str):
        return parse_layers(layers)
    return layers


def compile_project(
    root: str | Path = ".",
    *,
    source: str | Path | None = None,
    layers: str | set[str] | None = None,
    render_audit: bool = True,
) -> dict[str, Any]:
    """Compile a spec workspace into its generated artifact tree."""

    project_root = Path(root).resolve()
    source_path = (project_root / source).resolve() if source else default_source_path(project_root).resolve()
    return write_compiled(project_root, source_path, layers=_coerce_layers(layers), render_audit=render_audit)


def validate_project(
    root: str | Path = ".",
    *,
    layers: str | set[str] | None = None,
    release: bool = False,
) -> None:
    """Validate a spec workspace and its generated artifacts."""

    _validate_project(Path(root).resolve(), layers=_coerce_layers(layers), release=release)


def expected_artifacts(contract: dict[str, Any], artifact_policy: ArtifactPolicy | None = None) -> set[str]:
    """Return the generated artifact paths implied by a compiled contract."""

    policy = artifact_policy or ArtifactPolicy()
    paths = {str(COMPILED_CONTRACT_PATH)} | {relative for relative, _, _ in projection_files(contract)} | audit_expected_files(contract)
    return policy.filter(paths)


def write_generated(
    root: str | Path,
    contract: dict[str, Any],
    *,
    artifact_policy: ArtifactPolicy | None = None,
    render_audit: bool = True,
) -> set[str]:
    """Write generated artifacts for an already compiled contract."""

    project_root = Path(root).resolve()
    generated = project_root / "generated"
    if generated.exists():
        shutil.rmtree(generated)
    compiled_path = project_root / COMPILED_CONTRACT_PATH
    compiled_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(compiled_path, contract)
    for relative, content, kind in projection_files(contract):
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "json":
            write_json(path, content)
        elif kind == "yaml":
            write_yaml(path, content)
        elif kind == "text":
            path.write_text(content, encoding="utf-8")
    if render_audit:
        generate_audit(project_root, contract)
    return expected_artifacts(contract, artifact_policy=artifact_policy)
