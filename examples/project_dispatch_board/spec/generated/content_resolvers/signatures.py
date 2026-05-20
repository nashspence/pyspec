"""Generated content resolver signatures. Do not edit by hand."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyspec_contract.content import ContentContext, MediaAssetResult

@dataclass(frozen=True)
class TextResourceProjectActivityEmptyBodyArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectActivityEmptyHeadingArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectActivityReadyHeadingArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectApproveAccessDeniedArgs:
    message: str

@dataclass(frozen=True)
class TextResourceProjectApproveAuthenticationRequiredArgs:
    message: str

@dataclass(frozen=True)
class TextResourceProjectApproveLifecycleTransitionNotAllowedArgs:
    message: str

@dataclass(frozen=True)
class TextResourceProjectApproveNotFoundArgs:
    message: str

@dataclass(frozen=True)
class TextResourceProjectApproveSuccessArgs:
    project_id: str

@dataclass(frozen=True)
class TextResourceProjectApproveUnavailableArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectBoardOpenedArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectDetailErrorBodyArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectDetailErrorHeadingArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectDetailLoadingMessageArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectDetailNoneBodyArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectDetailNoneHeadingArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectDetailReadyHeadingArgs:
    customer: str
    title: str

@dataclass(frozen=True)
class TextResourceProjectListEmptyBodyArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectListEmptyHeadingArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectListErrorBodyArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectListErrorHeadingArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectListLoadingMessageArgs:
    pass

@dataclass(frozen=True)
class TextResourceProjectListReadyHeadingArgs:
    pass

@dataclass(frozen=True)
class MediaAssetProjectDetailReadyPriorityBadgeArgs:
    priority: str

@dataclass(frozen=True)
class MediaAssetProjectListEmptyIllustrationArgs:
    pass

TEXT_RESOURCE_SIGNATURES = {'text_resource.project.activity.empty.body': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectActivityEmptyBodyArgs'}, 'text_resource.project.activity.empty.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectActivityEmptyHeadingArgs'}, 'text_resource.project.activity.ready.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectActivityReadyHeadingArgs'}, 'text_resource.project.approve.access_denied': {'args': {'message': {'type': 'string'}}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectApproveAccessDeniedArgs'}, 'text_resource.project.approve.authentication_required': {'args': {'message': {'type': 'string'}}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectApproveAuthenticationRequiredArgs'}, 'text_resource.project.approve.lifecycle_transition_not_allowed': {'args': {'message': {'type': 'string'}}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectApproveLifecycleTransitionNotAllowedArgs'}, 'text_resource.project.approve.not_found': {'args': {'message': {'type': 'string'}}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectApproveNotFoundArgs'}, 'text_resource.project.approve.success': {'args': {'project_id': {'type': 'string'}}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectApproveSuccessArgs'}, 'text_resource.project.approve.unavailable': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectApproveUnavailableArgs'}, 'text_resource.project.board.opened': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectBoardOpenedArgs'}, 'text_resource.project.detail.error.body': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectDetailErrorBodyArgs'}, 'text_resource.project.detail.error.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectDetailErrorHeadingArgs'}, 'text_resource.project.detail.loading.message': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectDetailLoadingMessageArgs'}, 'text_resource.project.detail.none.body': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectDetailNoneBodyArgs'}, 'text_resource.project.detail.none.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectDetailNoneHeadingArgs'}, 'text_resource.project.detail.ready.heading': {'args': {'customer': {'type': 'string'}, 'title': {'type': 'string'}}, 'resolver_ref': 'text_resource.project.detail.ready.heading', 'arg_class': 'TextResourceProjectDetailReadyHeadingArgs'}, 'text_resource.project.list.empty.body': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectListEmptyBodyArgs'}, 'text_resource.project.list.empty.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectListEmptyHeadingArgs'}, 'text_resource.project.list.error.body': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectListErrorBodyArgs'}, 'text_resource.project.list.error.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectListErrorHeadingArgs'}, 'text_resource.project.list.loading.message': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectListLoadingMessageArgs'}, 'text_resource.project.list.ready.heading': {'args': {}, 'resolver_ref': None, 'arg_class': 'TextResourceProjectListReadyHeadingArgs'}}
MEDIA_ASSET_SIGNATURES = {'media_asset.project.detail.ready.priority_badge': {'args': {'priority': {'type': 'string'}}, 'resolver_ref': 'media_asset.project.detail.ready.priority_badge', 'arg_class': 'MediaAssetProjectDetailReadyPriorityBadgeArgs'}, 'media_asset.project.list.empty.illustration': {'args': {}, 'resolver_ref': None, 'arg_class': 'MediaAssetProjectListEmptyIllustrationArgs'}}
TEXT_RESOURCE_ARG_CLASSES = {'text_resource.project.activity.empty.body': TextResourceProjectActivityEmptyBodyArgs, 'text_resource.project.activity.empty.heading': TextResourceProjectActivityEmptyHeadingArgs, 'text_resource.project.activity.ready.heading': TextResourceProjectActivityReadyHeadingArgs, 'text_resource.project.approve.access_denied': TextResourceProjectApproveAccessDeniedArgs, 'text_resource.project.approve.authentication_required': TextResourceProjectApproveAuthenticationRequiredArgs, 'text_resource.project.approve.lifecycle_transition_not_allowed': TextResourceProjectApproveLifecycleTransitionNotAllowedArgs, 'text_resource.project.approve.not_found': TextResourceProjectApproveNotFoundArgs, 'text_resource.project.approve.success': TextResourceProjectApproveSuccessArgs, 'text_resource.project.approve.unavailable': TextResourceProjectApproveUnavailableArgs, 'text_resource.project.board.opened': TextResourceProjectBoardOpenedArgs, 'text_resource.project.detail.error.body': TextResourceProjectDetailErrorBodyArgs, 'text_resource.project.detail.error.heading': TextResourceProjectDetailErrorHeadingArgs, 'text_resource.project.detail.loading.message': TextResourceProjectDetailLoadingMessageArgs, 'text_resource.project.detail.none.body': TextResourceProjectDetailNoneBodyArgs, 'text_resource.project.detail.none.heading': TextResourceProjectDetailNoneHeadingArgs, 'text_resource.project.detail.ready.heading': TextResourceProjectDetailReadyHeadingArgs, 'text_resource.project.list.empty.body': TextResourceProjectListEmptyBodyArgs, 'text_resource.project.list.empty.heading': TextResourceProjectListEmptyHeadingArgs, 'text_resource.project.list.error.body': TextResourceProjectListErrorBodyArgs, 'text_resource.project.list.error.heading': TextResourceProjectListErrorHeadingArgs, 'text_resource.project.list.loading.message': TextResourceProjectListLoadingMessageArgs, 'text_resource.project.list.ready.heading': TextResourceProjectListReadyHeadingArgs}
MEDIA_ASSET_ARG_CLASSES = {'media_asset.project.detail.ready.priority_badge': MediaAssetProjectDetailReadyPriorityBadgeArgs, 'media_asset.project.list.empty.illustration': MediaAssetProjectListEmptyIllustrationArgs}
