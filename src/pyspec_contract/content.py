from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .paths import RESOLVER_SPEC_PATH, SPEC_ROOT


class ContentError(ValueError):
    pass


@dataclass(frozen=True)
class ContentContext:
    surface: str = "audit"
    locale: str = "en-US"


@dataclass(frozen=True)
class AssetResult:
    mime_type: str
    body: str
    alt: str = ""


class ContentSourceRegistry:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._functions: dict[str, Callable[..., Any]] = {}

    def clear(self) -> None:
        self._functions.clear()

    def implements(self, ref: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
            if ref in self._functions:
                raise ContentError(f"Duplicate {self.kind} content source: {ref}")
            self._functions[ref] = func
            return func
        return decorate

    @property
    def refs(self) -> set[str]:
        return set(self._functions)

    def function(self, ref: str) -> Callable[..., Any]:
        try:
            return self._functions[ref]
        except KeyError as exc:
            raise ContentError(f"Missing {self.kind} content source: {ref}") from exc


text = ContentSourceRegistry("text")
asset = ContentSourceRegistry("asset")
_LOADED_ROOT: Path | None = None
_RESOLVER_MODULE_NAME = "_pyspec_contract_project_spec"


def load_resolvers(root: Path) -> None:
    global _LOADED_ROOT
    root = root.resolve()
    if _LOADED_ROOT == root:
        return
    _LOADED_ROOT = None
    text.clear()
    asset.clear()
    resolver_path = root / RESOLVER_SPEC_PATH
    if not resolver_path.is_file():
        raise ContentError("Missing spec/spec.py for final content resolvers")
    sys.modules.pop(_RESOLVER_MODULE_NAME, None)
    sys.path.insert(0, str(root / SPEC_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(_RESOLVER_MODULE_NAME, resolver_path)
        if spec is None or spec.loader is None:
            raise ContentError("Cannot load spec/spec.py for final content resolvers")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_RESOLVER_MODULE_NAME] = module
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(root / SPEC_ROOT))
        except ValueError:
            pass
    _LOADED_ROOT = root


def _content_contract(root: Path):
    sys.path.insert(0, str(root / SPEC_ROOT))
    try:
        sys.modules.pop("generated.content_resolvers.signatures", None)
        return importlib.import_module("generated.content_resolvers.signatures")
    finally:
        try:
            sys.path.remove(str(root / SPEC_ROOT))
        except ValueError:
            pass


def instantiate_args(root: Path, kind: str, ref: str, values: Mapping[str, Any]) -> Any:
    module = _content_contract(root)
    if kind == "text":
        classes = module.TEXT_ARG_CLASSES
        kind_label = "text"
    else:
        classes = module.ASSET_ARG_CLASSES
        kind_label = kind
    try:
        arg_cls = classes[ref]
    except KeyError as exc:
        raise ContentError(f"Unknown {kind_label} content ref: {ref}") from exc
    return arg_cls(**dict(values))


def validate_resolver_function(func: Callable[..., Any], arg_class: type) -> None:
    signature = inspect.signature(func)
    params = list(signature.parameters.values())
    if len(params) != 2:
        raise ContentError(f"Resolver {func.__name__} must accept exactly (args, ctx)")
    if params[0].name != "args" or params[1].name != "ctx":
        raise ContentError(f"Resolver {func.__name__} parameters must be named args, ctx")
    annotation = params[0].annotation
    if annotation is not inspect._empty and annotation is not arg_class and annotation != arg_class.__name__:
        raise ContentError(f"Resolver {func.__name__} args annotation must be {arg_class.__name__}")


def call_text(root: Path, ref: str, values: Mapping[str, Any], ctx: ContentContext | None = None) -> str:
    load_resolvers(root)
    args = instantiate_args(root, "text", ref, values)
    result = text.function(ref)(args, ctx or ContentContext())
    if not isinstance(result, str):
        raise ContentError(f"Text source {ref} must return str")
    return result


def call_asset(root: Path, ref: str, values: Mapping[str, Any], ctx: ContentContext | None = None) -> AssetResult:
    load_resolvers(root)
    args = instantiate_args(root, "asset", ref, values)
    result = asset.function(ref)(args, ctx or ContentContext())
    if not isinstance(result, AssetResult):
        raise ContentError(f"Asset source {ref} must return AssetResult")
    return result
