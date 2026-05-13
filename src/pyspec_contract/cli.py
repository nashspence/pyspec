from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .api import compile_project, validate_project
from .audit import generate_audit
from .compile import ContractError
from .io import read_yaml
from .paths import COMPILED_CONTRACT_PATH, SOURCE_CONTRACT_PATH


MINIMAL_CONTRACT = """project: new_product_spec
resources:
  Item:
    kind: aggregate
    fields:
      id: ID
      title: Text
    basis: Item is the first product concept in this specification.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pyspec", description="Compile and validate whole-app product specifications.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a minimal contract.yaml")
    init_parser.add_argument("root", nargs="?", default=".")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing contract.yaml")

    compile_parser = subparsers.add_parser("compile", help="Compile contract.yaml into generated artifacts")
    compile_parser.add_argument("root", nargs="?", default=".")
    compile_parser.add_argument("--source", default=None, help="Source file relative to the project root")
    compile_parser.add_argument("--layers", default=None, help="Comma-separated authoring layers")
    compile_parser.add_argument("--no-audit", action="store_true", help="Skip visual audit rendering")

    validate_parser = subparsers.add_parser("validate", help="Validate a spec workspace and generated artifacts")
    validate_parser.add_argument("root", nargs="?", default=".")
    validate_parser.add_argument("--layers", default=None, help="Comma-separated authoring layers")
    validate_parser.add_argument("--release", action="store_true", help="Apply release gate checks")

    check_parser = subparsers.add_parser("check", help="Compile then validate")
    check_parser.add_argument("root", nargs="?", default=".")
    check_parser.add_argument("--source", default=None, help="Source file relative to the project root")
    check_parser.add_argument("--layers", default=None, help="Comma-separated authoring layers")
    check_parser.add_argument("--no-audit", action="store_true", help="Skip visual audit rendering")
    check_parser.add_argument("--release", action="store_true", help="Apply release gate checks")

    audit_parser = subparsers.add_parser("audit", help="Regenerate visual audit artifacts from generated/contract.complete.yaml")
    audit_parser.add_argument("root", nargs="?", default=".")

    clean_parser = subparsers.add_parser("clean-generated", help="Remove the generated artifact directory")
    clean_parser.add_argument("root", nargs="?", default=".")

    args = parser.parse_args(argv)
    try:
        root = Path(getattr(args, "root", ".")).resolve()
        if args.command == "init":
            path = root / SOURCE_CONTRACT_PATH
            if path.exists() and not args.force:
                raise ContractError(f"{SOURCE_CONTRACT_PATH} already exists; pass --force to overwrite")
            root.mkdir(parents=True, exist_ok=True)
            path.write_text(MINIMAL_CONTRACT, encoding="utf-8")
            print(f"created {path.relative_to(root)}")
            return 0

        if args.command == "compile":
            compile_project(root, source=args.source, layers=args.layers, render_audit=not args.no_audit)
            print("compiled")
            return 0

        if args.command == "validate":
            validate_project(root, layers=args.layers, release=args.release)
            print("contract ok")
            return 0

        if args.command == "check":
            compile_project(root, source=args.source, layers=args.layers, render_audit=not args.no_audit)
            validate_project(root, layers=args.layers, release=args.release)
            print("contract ok")
            return 0

        if args.command == "audit":
            contract = read_yaml(root / COMPILED_CONTRACT_PATH)
            generate_audit(root, contract)
            print("audit ok")
            return 0

        if args.command == "clean-generated":
            shutil.rmtree(root / "generated", ignore_errors=True)
            print("generated removed")
            return 0

    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
