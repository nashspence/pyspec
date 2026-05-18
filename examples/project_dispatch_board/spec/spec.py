from __future__ import annotations

import html

from pyspec_contract.content import AssetResult, ContentContext, asset, text
from generated.content_resolvers.signatures import AssetProjectDetailReadyPriorityBadgeArgs, TextProjectDetailReadyHeadingArgs
from generated.test_adapters.python_refs import MediaAsset, TextResource


@text.implements(TextResource.TEXT_PROJECT_DETAIL_READY_HEADING)
def project_detail_ready_heading(args: TextProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    return f"{args.title} · {args.customer}"


@asset.implements(MediaAsset.ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def project_detail_ready_priority_badge(args: AssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> AssetResult:
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
    return AssetResult(mime_type="image/svg+xml", body=svg, alt=f"{priority_attr} priority")
