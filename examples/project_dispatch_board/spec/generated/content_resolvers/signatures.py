"""Generated content source signatures. Do not edit by hand."""
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
class TextProjectApproveForbiddenArgs:
    message: str

@dataclass(frozen=True)
class TextProjectApproveNotFoundArgs:
    message: str

@dataclass(frozen=True)
class TextProjectApproveSuccessArgs:
    project_id: str

@dataclass(frozen=True)
class TextProjectApproveTransitionNotAllowedArgs:
    message: str

@dataclass(frozen=True)
class TextProjectApproveUnauthenticatedArgs:
    message: str

@dataclass(frozen=True)
class TextProjectApproveUnavailableArgs:
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

TEXT_SIGNATURES = {'text.project.activity.empty.body': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectActivityEmptyBodyArgs'}, 'text.project.activity.empty.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectActivityEmptyHeadingArgs'}, 'text.project.activity.ready.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectActivityReadyHeadingArgs'}, 'text.project.approve.forbidden': {'args': {'message': {'primitive': 'Text'}}, 'source_ref': None, 'arg_class': 'TextProjectApproveForbiddenArgs'}, 'text.project.approve.not_found': {'args': {'message': {'primitive': 'Text'}}, 'source_ref': None, 'arg_class': 'TextProjectApproveNotFoundArgs'}, 'text.project.approve.success': {'args': {'project_id': {'primitive': 'ID'}}, 'source_ref': None, 'arg_class': 'TextProjectApproveSuccessArgs'}, 'text.project.approve.transition_not_allowed': {'args': {'message': {'primitive': 'Text'}}, 'source_ref': None, 'arg_class': 'TextProjectApproveTransitionNotAllowedArgs'}, 'text.project.approve.unauthenticated': {'args': {'message': {'primitive': 'Text'}}, 'source_ref': None, 'arg_class': 'TextProjectApproveUnauthenticatedArgs'}, 'text.project.approve.unavailable': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectApproveUnavailableArgs'}, 'text.project.detail.error.body': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectDetailErrorBodyArgs'}, 'text.project.detail.error.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectDetailErrorHeadingArgs'}, 'text.project.detail.loading.message': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectDetailLoadingMessageArgs'}, 'text.project.detail.none.body': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectDetailNoneBodyArgs'}, 'text.project.detail.none.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectDetailNoneHeadingArgs'}, 'text.project.detail.ready.heading': {'args': {'customer': {'primitive': 'Text'}, 'title': {'primitive': 'Text'}}, 'source_ref': 'text.project.detail.ready.heading', 'arg_class': 'TextProjectDetailReadyHeadingArgs'}, 'text.project.list.empty.body': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectListEmptyBodyArgs'}, 'text.project.list.empty.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectListEmptyHeadingArgs'}, 'text.project.list.error.body': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectListErrorBodyArgs'}, 'text.project.list.error.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectListErrorHeadingArgs'}, 'text.project.list.loading.message': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectListLoadingMessageArgs'}, 'text.project.list.ready.heading': {'args': {}, 'source_ref': None, 'arg_class': 'TextProjectListReadyHeadingArgs'}}
ASSET_SIGNATURES = {'asset.project.detail.ready.priority_badge': {'args': {'priority': {'primitive': 'Text'}}, 'source_ref': 'asset.project.detail.ready.priority_badge', 'arg_class': 'AssetProjectDetailReadyPriorityBadgeArgs'}, 'asset.project.list.empty.illustration': {'args': {}, 'source_ref': None, 'arg_class': 'AssetProjectListEmptyIllustrationArgs'}}
TEXT_ARG_CLASSES = {'text.project.activity.empty.body': TextProjectActivityEmptyBodyArgs, 'text.project.activity.empty.heading': TextProjectActivityEmptyHeadingArgs, 'text.project.activity.ready.heading': TextProjectActivityReadyHeadingArgs, 'text.project.approve.forbidden': TextProjectApproveForbiddenArgs, 'text.project.approve.not_found': TextProjectApproveNotFoundArgs, 'text.project.approve.success': TextProjectApproveSuccessArgs, 'text.project.approve.transition_not_allowed': TextProjectApproveTransitionNotAllowedArgs, 'text.project.approve.unauthenticated': TextProjectApproveUnauthenticatedArgs, 'text.project.approve.unavailable': TextProjectApproveUnavailableArgs, 'text.project.detail.error.body': TextProjectDetailErrorBodyArgs, 'text.project.detail.error.heading': TextProjectDetailErrorHeadingArgs, 'text.project.detail.loading.message': TextProjectDetailLoadingMessageArgs, 'text.project.detail.none.body': TextProjectDetailNoneBodyArgs, 'text.project.detail.none.heading': TextProjectDetailNoneHeadingArgs, 'text.project.detail.ready.heading': TextProjectDetailReadyHeadingArgs, 'text.project.list.empty.body': TextProjectListEmptyBodyArgs, 'text.project.list.empty.heading': TextProjectListEmptyHeadingArgs, 'text.project.list.error.body': TextProjectListErrorBodyArgs, 'text.project.list.error.heading': TextProjectListErrorHeadingArgs, 'text.project.list.loading.message': TextProjectListLoadingMessageArgs, 'text.project.list.ready.heading': TextProjectListReadyHeadingArgs}
ASSET_ARG_CLASSES = {'asset.project.detail.ready.priority_badge': AssetProjectDetailReadyPriorityBadgeArgs, 'asset.project.list.empty.illustration': AssetProjectListEmptyIllustrationArgs}
