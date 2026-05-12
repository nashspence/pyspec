from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .compile import ContractError, compile_patch, validate_against_schema, write_compiled
from .io import read_yaml
from .project import projection_files
from .audit import audit_expected_files
from .guardrails import assert_prod_harness_is_real
from .projection_validators import validate_generated_projections


def validate_project(root: Path, release: bool = False) -> None:
    patch_path = root / "pm.patch.yaml"
    contract_path = root / "contract.yaml"
    if not patch_path.exists():
        raise ContractError("Missing pm.patch.yaml")
    if not contract_path.exists():
        raise ContractError("Missing contract.yaml; run python -m pm_contract.compile")

    patch = read_yaml(patch_path)
    compiled = compile_patch(patch)
    on_disk = read_yaml(contract_path)
    validate_against_schema(on_disk, "contract.schema.json")
    if compiled != on_disk:
        raise ContractError("contract.yaml is stale or hand-edited; run python -m pm_contract.compile pm.patch.yaml --out .")

    if release:
        _release_gate(compiled)

    if any("prod" in sc["harnesses"] for sc in compiled["scenarios"].values()):
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
        write_compiled(tmp_root, tmp_root / "pm.patch.yaml", tools_root=root, render_audit=False)
        expected_without_audit = {"contract.yaml"} | {relative for relative, _, _ in projection_files(compiled)}
        for relative in sorted(expected_without_audit):
            expected_path = tmp_root / relative
            actual_path = root / relative
            if not actual_path.exists():
                raise ContractError(f"Missing generated file: {relative}")
            if not filecmp.cmp(expected_path, actual_path, shallow=False):
                raise ContractError(f"Generated file is stale or hand-edited: {relative}")

    validate_generated_projections(root, compiled)


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
    if contract["status"] != "approved":
        raise ContractError("Release gate requires status: approved")
    blockers = [flag for flag in contract.get("review_flags", []) if flag.get("blocks_release")]
    if blockers:
        raise ContractError("Release gate blocked by review_flags: " + ", ".join(flag["id"] for flag in blockers))
    reviewed = []
    for section in ["resources", "capabilities", "views", "entries", "workflows", "scenarios"]:
        for item_id, item in contract.get(section, {}).items():
            basis = item.get("basis") if isinstance(item, dict) else None
            if isinstance(basis, dict) and basis.get("review"):
                reviewed.append(f"{section}.{item_id}")
    if reviewed:
        raise ContractError("Release gate blocked by basis.review=true: " + ", ".join(reviewed))
    placeholder_content = []
    for section in ["copies", "assets"]:
        for ref, item in contract.get(section, {}).items():
            if (item.get("final") or {}).get("status") != "approved":
                placeholder_content.append(ref)
    if placeholder_content:
        raise ContractError("Release gate requires approved final content for: " + ", ".join(sorted(placeholder_content)))

    without_prod = [sid for sid, sc in contract["scenarios"].items() if "prod" not in sc["harnesses"]]
    if without_prod:
        raise ContractError("Release gate requires prod harness coverage for scenarios: " + ", ".join(without_prod))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pm.patch.yaml, contract.yaml, and generated projections.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_project(Path(args.root).resolve(), release=args.release)
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("contract ok")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
