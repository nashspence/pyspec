from __future__ import annotations

import html

from pyspec_contract.content import ContentContext, MediaAssetResult, media_asset, text_resource
from generated.content_resolvers.signatures import MediaAssetProjectDetailReadyPriorityBadgeArgs, TextResourceProjectDetailReadyHeadingArgs
from generated.test_adapters.python_refs import MediaAsset, TextResource


@text_resource.implements(TextResource.TEXT_RESOURCE_PROJECT_DETAIL_READY_HEADING)
def project_detail_ready_heading(args: TextResourceProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    return f"{args.title} · {args.customer}"


@media_asset.implements(MediaAsset.MEDIA_ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def project_detail_ready_priority_badge(args: MediaAssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> MediaAssetResult:
    priority = str(args.priority).strip() or "Priority"
    priority_text = html.escape(priority, quote=False)
    priority_attr = html.escape(priority, quote=True)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120" role="img" aria-label="{priority_attr} priority">
  <title>{priority_text} priority</title>
  <rect x="16" y="18" width="288" height="84" rx="28" fill="#f4f4f5" stroke="#52525b" stroke-width="3"/>
  <circle cx="70" cy="60" r="20" fill="#d4d4d8" stroke="#52525b" stroke-width="3"/>
  <path d="M104 60 H252" stroke="#52525b" stroke-width="10" stroke-linecap="round"/>
  <text x="160" y="69" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="28" font-weight="700" fill="#18181b">{priority_text}</text>
</svg>
'''
    return MediaAssetResult(mime_type="image/svg+xml", body=svg, alt=f"{priority_attr} priority")
