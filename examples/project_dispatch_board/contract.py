from __future__ import annotations

from pyspec_contract.content import AssetResult, ContentContext, asset, copy
from generated.content_contract import AssetProjectDetailReadyPriorityBadgeArgs, CopyProjectDetailReadyHeadingArgs
from generated.refs import Asset, Copy


@copy.implements(Copy.COPY_PROJECT_DETAIL_READY_HEADING)
def project_detail_ready_heading(args: CopyProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    return f"{args.title} · {args.customer}"


@asset.implements(Asset.ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def project_detail_ready_priority_badge(args: AssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> AssetResult:
    priority = str(args.priority).strip() or "Priority"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120" role="img" aria-label="{priority} priority">
  <title>{priority} priority</title>
  <rect x="16" y="18" width="288" height="84" rx="28" fill="#f4f4f5" stroke="#52525b" stroke-width="3"/>
  <circle cx="70" cy="60" r="20" fill="#d4d4d8" stroke="#52525b" stroke-width="3"/>
  <path d="M104 60 H252" stroke="#52525b" stroke-width="10" stroke-linecap="round"/>
  <text x="160" y="69" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="28" font-weight="700" fill="#18181b">{priority}</text>
</svg>
'''
    return AssetResult(mime_type="image/svg+xml", body=svg, alt=f"{priority} priority")
