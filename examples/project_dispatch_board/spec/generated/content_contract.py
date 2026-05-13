"""Generated content resolver contract. Do not edit by hand."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyspec_contract.content import AssetResult, ContentContext

@dataclass(frozen=True)
class CopyProjectActivityEmptyBodyArgs:
    pass

@dataclass(frozen=True)
class CopyProjectActivityEmptyHeadingArgs:
    pass

@dataclass(frozen=True)
class CopyProjectActivityReadyHeadingArgs:
    pass

@dataclass(frozen=True)
class CopyProjectDetailErrorBodyArgs:
    pass

@dataclass(frozen=True)
class CopyProjectDetailErrorHeadingArgs:
    pass

@dataclass(frozen=True)
class CopyProjectDetailLoadingMessageArgs:
    pass

@dataclass(frozen=True)
class CopyProjectDetailNoneBodyArgs:
    pass

@dataclass(frozen=True)
class CopyProjectDetailNoneHeadingArgs:
    pass

@dataclass(frozen=True)
class CopyProjectDetailReadyHeadingArgs:
    customer: str
    title: str

@dataclass(frozen=True)
class CopyProjectListEmptyBodyArgs:
    pass

@dataclass(frozen=True)
class CopyProjectListEmptyHeadingArgs:
    pass

@dataclass(frozen=True)
class CopyProjectListErrorBodyArgs:
    pass

@dataclass(frozen=True)
class CopyProjectListErrorHeadingArgs:
    pass

@dataclass(frozen=True)
class CopyProjectListLoadingMessageArgs:
    pass

@dataclass(frozen=True)
class CopyProjectListReadyHeadingArgs:
    pass

@dataclass(frozen=True)
class AssetProjectDetailReadyPriorityBadgeArgs:
    priority: str

@dataclass(frozen=True)
class AssetProjectListEmptyIllustrationArgs:
    pass

COPY_SIGNATURES = {'copy.project.activity.empty.body': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectActivityEmptyBodyArgs'}, 'copy.project.activity.empty.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectActivityEmptyHeadingArgs'}, 'copy.project.activity.ready.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectActivityReadyHeadingArgs'}, 'copy.project.detail.error.body': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectDetailErrorBodyArgs'}, 'copy.project.detail.error.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectDetailErrorHeadingArgs'}, 'copy.project.detail.loading.message': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectDetailLoadingMessageArgs'}, 'copy.project.detail.none.body': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectDetailNoneBodyArgs'}, 'copy.project.detail.none.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectDetailNoneHeadingArgs'}, 'copy.project.detail.ready.heading': {'args': {'customer': 'Text', 'title': 'Text'}, 'resolver': 'copy.project.detail.ready.heading', 'arg_class': 'CopyProjectDetailReadyHeadingArgs'}, 'copy.project.list.empty.body': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectListEmptyBodyArgs'}, 'copy.project.list.empty.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectListEmptyHeadingArgs'}, 'copy.project.list.error.body': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectListErrorBodyArgs'}, 'copy.project.list.error.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectListErrorHeadingArgs'}, 'copy.project.list.loading.message': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectListLoadingMessageArgs'}, 'copy.project.list.ready.heading': {'args': {}, 'resolver': None, 'arg_class': 'CopyProjectListReadyHeadingArgs'}}
ASSET_SIGNATURES = {'asset.project.detail.ready.priority_badge': {'args': {'priority': 'Text'}, 'resolver': 'asset.project.detail.ready.priority_badge', 'arg_class': 'AssetProjectDetailReadyPriorityBadgeArgs'}, 'asset.project.list.empty.illustration': {'args': {}, 'resolver': None, 'arg_class': 'AssetProjectListEmptyIllustrationArgs'}}
COPY_ARG_CLASSES = {'copy.project.activity.empty.body': CopyProjectActivityEmptyBodyArgs, 'copy.project.activity.empty.heading': CopyProjectActivityEmptyHeadingArgs, 'copy.project.activity.ready.heading': CopyProjectActivityReadyHeadingArgs, 'copy.project.detail.error.body': CopyProjectDetailErrorBodyArgs, 'copy.project.detail.error.heading': CopyProjectDetailErrorHeadingArgs, 'copy.project.detail.loading.message': CopyProjectDetailLoadingMessageArgs, 'copy.project.detail.none.body': CopyProjectDetailNoneBodyArgs, 'copy.project.detail.none.heading': CopyProjectDetailNoneHeadingArgs, 'copy.project.detail.ready.heading': CopyProjectDetailReadyHeadingArgs, 'copy.project.list.empty.body': CopyProjectListEmptyBodyArgs, 'copy.project.list.empty.heading': CopyProjectListEmptyHeadingArgs, 'copy.project.list.error.body': CopyProjectListErrorBodyArgs, 'copy.project.list.error.heading': CopyProjectListErrorHeadingArgs, 'copy.project.list.loading.message': CopyProjectListLoadingMessageArgs, 'copy.project.list.ready.heading': CopyProjectListReadyHeadingArgs}
ASSET_ARG_CLASSES = {'asset.project.detail.ready.priority_badge': AssetProjectDetailReadyPriorityBadgeArgs, 'asset.project.list.empty.illustration': AssetProjectListEmptyIllustrationArgs}
