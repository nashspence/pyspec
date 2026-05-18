"""Generated content source stubs. Do not edit; move needed functions into spec.py."""
from __future__ import annotations

from pyspec_contract.content import AssetResult, ContentContext, asset, text
from generated.content_resolvers.signatures import *  # generated arg classes
from generated.test_adapters.python_refs import MediaAsset, TextResource

@text.implements(TextResource.TEXT_PROJECT_DETAIL_READY_HEADING)
def text_project_detail_ready_heading(args: TextProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    raise NotImplementedError('text.project.detail.ready.heading')

@asset.implements(MediaAsset.ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def asset_project_detail_ready_priority_badge(args: AssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> AssetResult:
    raise NotImplementedError('asset.project.detail.ready.priority_badge')
