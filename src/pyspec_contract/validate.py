from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .compile import ContractError, author_from_source, compile_author, default_source_path, validate_against_schema, write_compiled
from .layers import parse_layers
from .io import read_yaml, yaml_contains_anchors
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR, SOURCE_SPEC_PATH
from .project import projection_files
from .audit import audit_expected_files
from .guardrails import assert_prod_harness_is_real
from .projection_validators import validate_generated_projections


def validate_project(root: Path, release: bool = False, layers: set[str] | None = None) -> None:
    source_contract_path = root / SOURCE_SPEC_PATH
    compiled_contract_path = root / COMPILED_SPEC_PATH
    if not source_contract_path.exists():
        raise ContractError("Missing spec/spec.yaml")
    if not compiled_contract_path.exists():
        raise ContractError("Missing spec/generated/compiled/spec.yaml; run pyspec compile")

    _assert_generated_yaml_is_plain(root)

    source_path = default_source_path(root)
    source = read_yaml(source_path)
    author = author_from_source(source, layers=layers)
    validate_against_schema(author, "author.schema.json")

    compiled = compile_author(author, layers=layers)
    on_disk = read_yaml(compiled_contract_path)
    validate_against_schema(on_disk, "spec.schema.json")
    if compiled != on_disk:
        raise ContractError("spec/generated/compiled/spec.yaml is stale or hand-edited; run pyspec compile")

    if release:
        _release_gate(compiled)

    if compiled["scenarios"]:
        assert_prod_harness_is_real(root)

    expected = {str(COMPILED_SPEC_PATH)} | {relative for relative, _, _ in projection_files(compiled, layers=layers)} | audit_expected_files(compiled)
    actual = _generated_files(root)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        messages = []
        if extra:
            messages.append("extra generated files: " + ", ".join(extra))
        if missing:
            messages.append("missing generated files: " + ", ".join(missing))
        raise ContractError("Generated file set drift: " + "; ".join(messages))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        tmp_source = tmp_root / source_path.name
        tmp_source.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        write_compiled(tmp_root, tmp_source, tools_root=root, render_audit=False, layers=layers)
        expected_without_audit = {str(COMPILED_SPEC_PATH)} | {relative for relative, _, _ in projection_files(compiled, layers=layers)}
        for relative in sorted(expected_without_audit):
            expected_path = tmp_root / relative
            actual_path = root / relative
            if not actual_path.exists():
                raise ContractError(f"Missing generated file: {relative}")
            if not filecmp.cmp(expected_path, actual_path, shallow=False):
                raise ContractError(f"Generated file is stale or hand-edited: {relative}")

    validate_generated_projections(root, compiled)


def _assert_generated_yaml_is_plain(root: Path) -> None:
    yaml_paths = []
    if (root / SOURCE_SPEC_PATH).exists():
        yaml_paths.append(root / SOURCE_SPEC_PATH)
    generated = root / GENERATED_SPEC_DIR
    if generated.exists():
        yaml_paths.extend(path for path in generated.rglob("*.yaml") if path.is_file())
    offenders = [str(path.relative_to(root)) for path in yaml_paths if yaml_contains_anchors(path)]
    if offenders:
        raise ContractError("Generated YAML must not contain anchors or aliases: " + ", ".join(sorted(offenders)))


def _generated_files(root: Path) -> set[str]:
    generated = root / GENERATED_SPEC_DIR
    if not generated.exists():
        return set()
    files = set()
    for path in generated.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        files.add(str(path.relative_to(root)))
    return files


def _release_gate(contract: dict[str, Any]) -> None:
    """External release policy; does not rely on contract metadata fields."""
    placeholder_content = []
    for section in ["text_resources", "assets"]:
        for ref, item in contract.get(section, {}).items():
            if not item.get("source_ref"):
                placeholder_content.append(ref)
    if placeholder_content:
        raise ContractError("Release gate requires final content resolvers for: " + ", ".join(sorted(placeholder_content)))



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate spec/spec.yaml, spec/generated/compiled/spec.yaml, and projections.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--layers", default=None, help="Comma-separated authoring layers to enforce while re-compiling the authored source")
    args = parser.parse_args(argv)
    try:
        validate_project(Path(args.root).resolve(), release=args.release, layers=parse_layers(args.layers))
    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("spec ok")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
