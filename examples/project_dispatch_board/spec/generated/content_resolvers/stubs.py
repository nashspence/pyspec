"""Generated content resolver stubs. Do not edit; copy needed functions into spec.py."""
from __future__ import annotations

from pyspec_contract.content import AssetResult, ContentContext, asset, copy
from generated.content_resolvers.signatures import *  # generated arg classes
from generated.test_adapters.python_refs import Asset, Copy

@copy.implements(Copy.COPY_PROJECT_DETAIL_READY_HEADING)
def copy_project_detail_ready_heading(args: CopyProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    raise NotImplementedError('copy.project.detail.ready.heading')

@asset.implements(Asset.ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def asset_project_detail_ready_priority_badge(args: AssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> AssetResult:
    raise NotImplementedError('asset.project.detail.ready.priority_badge')
