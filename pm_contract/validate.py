from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .compile import ContractError, compile_patch, validate_against_schema, write_compiled
from .layers import parse_layers
from .io import read_yaml, yaml_contains_anchors
from .project import projection_files
from .audit import audit_expected_files
from .guardrails import assert_prod_harness_is_real
from .projection_validators import validate_generated_projections


def validate_project(root: Path, release: bool = False, layers: set[str] | None = None) -> None:
    patch_path = root / "pm.patch.yaml"
    contract_path = root / "contract.yaml"
    if not patch_path.exists():
        raise ContractError("Missing pm.patch.yaml")
    if not contract_path.exists():
        raise ContractError("Missing contract.yaml; run python -m pm_contract.compile")

    _assert_generated_yaml_is_plain(root)

    patch = read_yaml(patch_path)
    compiled = compile_patch(patch, layers=layers)
    on_disk = read_yaml(contract_path)
    validate_against_schema(on_disk, "contract.schema.json")
    if compiled != on_disk:
        raise ContractError("contract.yaml is stale or hand-edited; run python -m pm_contract.compile pm.patch.yaml --out .")

    if release:
        _release_gate(compiled)

    if compiled["scenarios"]:
        assert_prod_harness_is_real(root)

    expected = {"contract.yaml"} | {relative for relative, _, _ in projection_files(compiled)} | audit_expected_files(compiled)
    actual = {"contract.yaml"} | _generated_files(root)
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
        shutil.copy2(patch_path, tmp_root / "pm.patch.yaml")
        write_compiled(tmp_root, tmp_root / "pm.patch.yaml", tools_root=root, render_audit=False, layers=layers)
        expected_without_audit = {"contract.yaml"} | {relative for relative, _, _ in projection_files(compiled)}
        for relative in sorted(expected_without_audit):
            expected_path = tmp_root / relative
            actual_path = root / relative
            if not actual_path.exists():
                raise ContractError(f"Missing generated file: {relative}")
            if not filecmp.cmp(expected_path, actual_path, shallow=False):
                raise ContractError(f"Generated file is stale or hand-edited: {relative}")

    validate_generated_projections(root, compiled)


def _assert_generated_yaml_is_plain(root: Path) -> None:
    yaml_paths = [root / "contract.yaml"]
    generated = root / "generated"
    if generated.exists():
        yaml_paths.extend(path for path in generated.rglob("*.yaml") if path.is_file())
    offenders = [str(path.relative_to(root)) for path in yaml_paths if yaml_contains_anchors(path)]
    if offenders:
        raise ContractError("Generated YAML must not contain anchors or aliases: " + ", ".join(sorted(offenders)))


def _generated_files(root: Path) -> set[str]:
    generated = root / "generated"
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
    for section in ["copies", "assets"]:
        for ref, item in contract.get(section, {}).items():
            if not item.get("resolver"):
                placeholder_content.append(ref)
    if placeholder_content:
        raise ContractError("Release gate requires final content resolvers for: " + ", ".join(sorted(placeholder_content)))



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pm.patch.yaml, contract.yaml, and generated projections.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--layers", default=None, help="Comma-separated authoring layers to enforce while re-compiling pm.patch.yaml")
    args = parser.parse_args(argv)
    try:
        validate_project(Path(args.root).resolve(), release=args.release, layers=parse_layers(args.layers))
    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("contract ok")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
