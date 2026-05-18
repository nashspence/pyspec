"""Generated content source stubs. Do not edit; move needed functions into spec.py."""
from __future__ import annotations

from pyspec_contract.content import ContentContext, MediaAssetResult, media_asset, text_resource
from generated.content_resolvers.signatures import *  # generated arg classes
from generated.test_adapters.python_refs import MediaAsset, TextResource

@text_resource.implements(TextResource.TEXT_RESOURCE_PROJECT_DETAIL_READY_HEADING)
def text_resource_project_detail_ready_heading(args: TextResourceProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    raise NotImplementedError('text_resource.project.detail.ready.heading')

@media_asset.implements(MediaAsset.MEDIA_ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def media_asset_project_detail_ready_priority_badge(args: MediaAssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> MediaAssetResult:
    raise NotImplementedError('media_asset.project.detail.ready.priority_badge')
