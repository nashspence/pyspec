from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


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


class ResolverRegistry:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._functions: dict[str, Callable[..., Any]] = {}

    def clear(self) -> None:
        self._functions.clear()

    def implements(self, ref: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
            if ref in self._functions:
                raise ContentError(f"Duplicate {self.kind} resolver: {ref}")
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
            raise ContentError(f"Missing {self.kind} resolver: {ref}") from exc


copy = ResolverRegistry("copy")
asset = ResolverRegistry("asset")
_LOADED_ROOT: Path | None = None


def load_resolvers(root: Path) -> None:
    global _LOADED_ROOT
    root = root.resolve()
    if _LOADED_ROOT == root:
        return
    copy.clear()
    asset.clear()
    for name in ["content.resolvers"]:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(root))
    try:
        importlib.import_module("content.resolvers")
    except ModuleNotFoundError as exc:
        if exc.name == "content" or exc.name == "content.resolvers":
            raise ContentError("Missing content/resolvers.py for final content resolvers") from exc
        raise
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
    _LOADED_ROOT = root


def _content_contract(root: Path):
    sys.path.insert(0, str(root))
    try:
        sys.modules.pop("generated.content_contract", None)
        return importlib.import_module("generated.content_contract")
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass


def instantiate_args(root: Path, kind: str, ref: str, values: Mapping[str, Any]) -> Any:
    module = _content_contract(root)
    classes = module.COPY_ARG_CLASSES if kind == "copy" else module.ASSET_ARG_CLASSES
    try:
        arg_cls = classes[ref]
    except KeyError as exc:
        raise ContentError(f"Unknown {kind} content ref: {ref}") from exc
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


def call_copy(root: Path, ref: str, values: Mapping[str, Any], ctx: ContentContext | None = None) -> str:
    load_resolvers(root)
    args = instantiate_args(root, "copy", ref, values)
    result = copy.function(ref)(args, ctx or ContentContext())
    if not isinstance(result, str):
        raise ContentError(f"Copy resolver {ref} must return str")
    return result


def call_asset(root: Path, ref: str, values: Mapping[str, Any], ctx: ContentContext | None = None) -> AssetResult:
    load_resolvers(root)
    args = instantiate_args(root, "asset", ref, values)
    result = asset.function(ref)(args, ctx or ContentContext())
    if not isinstance(result, AssetResult):
        raise ContentError(f"Asset resolver {ref} must return AssetResult")
    return result
