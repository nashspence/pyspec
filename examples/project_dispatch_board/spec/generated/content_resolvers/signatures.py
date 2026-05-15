"""Generated content resolver signatures. Do not edit by hand."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyspec_contract.content import AssetResult, ContentContext

@dataclass(frozen=True)
class TextProjectActivityEmptyBodyArgs:
    pass

@dataclass(frozen=True)
class TextProjectActivityEmptyHeadingArgs:
    pass

@dataclass(frozen=True)
class TextProjectActivityReadyHeadingArgs:
    pass

@dataclass(frozen=True)
class TextProjectDetailErrorBodyArgs:
    pass

@dataclass(frozen=True)
class TextProjectDetailErrorHeadingArgs:
    pass

@dataclass(frozen=True)
class TextProjectDetailLoadingMessageArgs:
    pass

@dataclass(frozen=True)
class TextProjectDetailNoneBodyArgs:
    pass

@dataclass(frozen=True)
class TextProjectDetailNoneHeadingArgs:
    pass

@dataclass(frozen=True)
class TextProjectDetailReadyHeadingArgs:
    customer: str
    title: str

@dataclass(frozen=True)
class TextProjectListEmptyBodyArgs:
    pass

@dataclass(frozen=True)
class TextProjectListEmptyHeadingArgs:
    pass

@dataclass(frozen=True)
class TextProjectListErrorBodyArgs:
    pass

@dataclass(frozen=True)
class TextProjectListErrorHeadingArgs:
    pass

@dataclass(frozen=True)
class TextProjectListLoadingMessageArgs:
    pass

@dataclass(frozen=True)
class TextProjectListReadyHeadingArgs:
    pass

@dataclass(frozen=True)
class AssetProjectDetailReadyPriorityBadgeArgs:
    priority: str

@dataclass(frozen=True)
class AssetProjectListEmptyIllustrationArgs:
    pass

COPY_SIGNATURES = {'text.project.activity.empty.body': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectActivityEmptyBodyArgs'}, 'text.project.activity.empty.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectActivityEmptyHeadingArgs'}, 'text.project.activity.ready.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectActivityReadyHeadingArgs'}, 'text.project.detail.error.body': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectDetailErrorBodyArgs'}, 'text.project.detail.error.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectDetailErrorHeadingArgs'}, 'text.project.detail.loading.message': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectDetailLoadingMessageArgs'}, 'text.project.detail.none.body': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectDetailNoneBodyArgs'}, 'text.project.detail.none.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectDetailNoneHeadingArgs'}, 'text.project.detail.ready.heading': {'args': {'customer': 'Text', 'title': 'Text'}, 'resolver': 'text.project.detail.ready.heading', 'arg_class': 'TextProjectDetailReadyHeadingArgs'}, 'text.project.list.empty.body': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectListEmptyBodyArgs'}, 'text.project.list.empty.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectListEmptyHeadingArgs'}, 'text.project.list.error.body': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectListErrorBodyArgs'}, 'text.project.list.error.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectListErrorHeadingArgs'}, 'text.project.list.loading.message': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectListLoadingMessageArgs'}, 'text.project.list.ready.heading': {'args': {}, 'resolver': None, 'arg_class': 'TextProjectListReadyHeadingArgs'}}
ASSET_SIGNATURES = {'asset.project.detail.ready.priority_badge': {'args': {'priority': 'Text'}, 'resolver': 'asset.project.detail.ready.priority_badge', 'arg_class': 'AssetProjectDetailReadyPriorityBadgeArgs'}, 'asset.project.list.empty.illustration': {'args': {}, 'resolver': None, 'arg_class': 'AssetProjectListEmptyIllustrationArgs'}}
COPY_ARG_CLASSES = {'text.project.activity.empty.body': TextProjectActivityEmptyBodyArgs, 'text.project.activity.empty.heading': TextProjectActivityEmptyHeadingArgs, 'text.project.activity.ready.heading': TextProjectActivityReadyHeadingArgs, 'text.project.detail.error.body': TextProjectDetailErrorBodyArgs, 'text.project.detail.error.heading': TextProjectDetailErrorHeadingArgs, 'text.project.detail.loading.message': TextProjectDetailLoadingMessageArgs, 'text.project.detail.none.body': TextProjectDetailNoneBodyArgs, 'text.project.detail.none.heading': TextProjectDetailNoneHeadingArgs, 'text.project.detail.ready.heading': TextProjectDetailReadyHeadingArgs, 'text.project.list.empty.body': TextProjectListEmptyBodyArgs, 'text.project.list.empty.heading': TextProjectListEmptyHeadingArgs, 'text.project.list.error.body': TextProjectListErrorBodyArgs, 'text.project.list.error.heading': TextProjectListErrorHeadingArgs, 'text.project.list.loading.message': TextProjectListLoadingMessageArgs, 'text.project.list.ready.heading': TextProjectListReadyHeadingArgs}
ASSET_ARG_CLASSES = {'asset.project.detail.ready.priority_badge': AssetProjectDetailReadyPriorityBadgeArgs, 'asset.project.list.empty.illustration': AssetProjectListEmptyIllustrationArgs}
