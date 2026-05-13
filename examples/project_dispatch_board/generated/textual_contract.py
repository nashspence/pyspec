from __future__ import annotations

# Generated Textual projection. Do not edit by hand.
# The PM contract owns views/states/actions/widgets/TCSS; a real Textual app imports this file
# and renders panels by id instead of inventing screens, widgets, or action keys.

PROJECT = 'project_dispatch_board'
SCREENS = [{'id': 'screen.project.board', 'entry': 'textual.project.board', 'view': 'project.board', 'command': 'project board', 'screen_class': 'ComposedContractScreen'}]
PANELS = [{'id': 'panel.project.board.ready', 'owner_kind': 'view', 'owner': 'project.board', 'state': 'ready', 'data': [], 'slots': {'copy': [], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}}, {'id': 'panel.project.activity.empty', 'owner_kind': 'panel', 'owner': 'panel.project.activity', 'state': 'empty', 'data': [], 'slots': {'copy': ['copy.project.activity.empty.heading', 'copy.project.activity.empty.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'empty', 'transitions': [{'event': 'project.selection_changed', 'from': 'empty', 'to': 'ready'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'event': 'selection.cleared', 'from': 'ready', 'to': 'empty'}], 'context': {'project_id': 'ID'}}}, {'id': 'panel.project.activity.ready', 'owner_kind': 'panel', 'owner': 'panel.project.activity', 'state': 'ready', 'data': [{'query': 'query.project.activity.read', 'capability': 'project.read'}], 'slots': {'copy': ['copy.project.activity.ready.heading'], 'assets': [], 'fields': ['updated_at', 'status', 'assignee'], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'empty', 'transitions': [{'event': 'project.selection_changed', 'from': 'empty', 'to': 'ready'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'event': 'selection.cleared', 'from': 'ready', 'to': 'empty'}], 'context': {'project_id': 'ID'}}}, {'id': 'panel.project.detail.error', 'owner_kind': 'panel', 'owner': 'panel.project.detail', 'state': 'error', 'data': [], 'slots': {'copy': ['copy.project.detail.error.heading', 'copy.project.detail.error.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'event': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'event': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'panel.project.detail.loading', 'owner_kind': 'panel', 'owner': 'panel.project.detail', 'state': 'loading', 'data': [{'query': 'query.project.detail.read', 'capability': 'project.read'}], 'slots': {'copy': ['copy.project.detail.loading.message'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'event': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'event': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'panel.project.detail.none', 'owner_kind': 'panel', 'owner': 'panel.project.detail', 'state': 'none', 'data': [], 'slots': {'copy': ['copy.project.detail.none.heading', 'copy.project.detail.none.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'event': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'event': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'panel.project.detail.ready', 'owner_kind': 'panel', 'owner': 'panel.project.detail', 'state': 'ready', 'data': [], 'slots': {'copy': ['copy.project.detail.ready.heading'], 'assets': ['asset.project.detail.ready.priority_badge'], 'fields': ['title', 'customer', 'status', 'assignee', 'summary'], 'actions': ['project.approve', 'project.archive']}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'event': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'event': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'panel.project.list.empty', 'owner_kind': 'panel', 'owner': 'panel.project.list', 'state': 'empty', 'data': [], 'slots': {'copy': ['copy.project.list.empty.heading', 'copy.project.list.empty.body'], 'assets': ['asset.project.list.empty.illustration'], 'fields': [], 'actions': ['project.create']}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'event': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'event': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': 'project.selected'}], 'event': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'panel.project.list.error', 'owner_kind': 'panel', 'owner': 'panel.project.list', 'state': 'error', 'data': [], 'slots': {'copy': ['copy.project.list.error.heading', 'copy.project.list.error.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'event': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'event': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': 'project.selected'}], 'event': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'panel.project.list.loading', 'owner_kind': 'panel', 'owner': 'panel.project.list', 'state': 'loading', 'data': [], 'slots': {'copy': ['copy.project.list.loading.message'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'event': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'event': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': 'project.selected'}], 'event': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'panel.project.list.ready', 'owner_kind': 'panel', 'owner': 'panel.project.list', 'state': 'ready', 'data': [], 'slots': {'copy': ['copy.project.list.ready.heading'], 'assets': [], 'fields': ['title', 'customer', 'priority', 'status'], 'actions': ['project.create', 'project.submit']}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'event': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'event': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'event': 'data.error', 'from': 'loading', 'to': 'error'}, {'event': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': 'project.selected'}], 'event': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}]
COMPOSITIONS = [{'id': 'project.board', 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}, 'layout': {'html': {'css': {'rules': [{'declarations': {'display': 'grid', 'gap': 'token.gap', 'grid-template-columns': 'token.nav_width 1fr token.aside_width'}, 'selector': 'root'}, {'declarations': {'min-width': 'token.nav_width'}, 'selector': 'region.nav'}, {'declarations': {'min-width': '0'}, 'selector': 'region.main'}, {'declarations': {'min-width': 'token.aside_width'}, 'selector': 'region.aside'}], 'tokens': {'aside_width': '16rem', 'gap': '1rem', 'nav_width': '20rem'}}, 'regions': {'aside': {'classes': ['dispatch-board-aside'], 'element': 'aside', 'order': 3, 'required': True, 'role': 'complementary'}, 'main': {'classes': ['dispatch-board-main'], 'element': 'main', 'order': 2, 'required': True, 'role': 'main'}, 'nav': {'classes': ['dispatch-board-nav'], 'element': 'nav', 'order': 1, 'required': True, 'role': 'navigation'}}, 'root': {'classes': ['dispatch-board'], 'element': 'section', 'role': 'region'}}, 'textual': {'containers': {'aside': {'id': 'aside', 'kind': 'Container', 'order': 3, 'required': True}, 'main': {'id': 'main', 'kind': 'Container', 'order': 2, 'required': True}, 'nav': {'id': 'nav', 'kind': 'Container', 'order': 1, 'required': True}}, 'screen_class': 'ProjectBoardScreen', 'tcss': {'rules': [{'declarations': {'layout': 'horizontal'}, 'selector': 'screen'}, {'declarations': {'width': '32'}, 'selector': 'region.nav'}, {'declarations': {'width': '28'}, 'selector': 'region.aside'}]}}}, 'instances': [{'context': {'selected_project_id': '$view.selected_project_id', 'workspace_id': '$view.workspace_id'}, 'id': 'list', 'initial': 'loading', 'panel': 'panel.project.list', 'region': 'nav'}, {'context': {'project_id': '$view.selected_project_id'}, 'id': 'detail', 'initial': 'none', 'panel': 'panel.project.detail', 'region': 'main', 'selected': {'state': 'loading', 'when': {'context_present': 'selected_project_id'}}}, {'context': {'project_id': '$view.selected_project_id'}, 'id': 'activity', 'initial': 'empty', 'panel': 'panel.project.activity', 'region': 'aside', 'selected': {'state': 'ready', 'when': {'context_present': 'selected_project_id'}}}], 'sync': [{'do': [{'set': {'context': 'selected_project_id', 'from': '$event.project_id'}}, {'send': {'event': 'project.selection_changed', 'panel': 'detail'}}, {'send': {'event': 'project.selection_changed', 'panel': 'activity'}}], 'id': 'select_project_updates_panels', 'when': {'emits': 'project.selected', 'panel': 'list'}}]}]
TCSS = '/* Generated Textual CSS contract. Do not edit. */\nScreen {\n  layout: vertical;\n}\n.contract-panel {\n  padding: 1;\n}\nProjectBoardScreen {\n  layout: horizontal;\n}\n#nav {\n  width: 32;\n}\n#aside {\n  width: 28;\n}\n'


def panel(panel_id: str) -> dict:
    for item in PANELS:
        if item["id"] == panel_id:
            return item
    raise KeyError(panel_id)


def composition(view_id: str) -> dict:
    for item in COMPOSITIONS:
        if item["id"] == view_id:
            return item
    raise KeyError(view_id)


def textual_css() -> str:
    return TCSS


def compose_contract_panel(panel_id: str) -> list[tuple[str, str]]:
    item = panel(panel_id)
    textual = (item.get("presentation") or {}).get("textual") or {}
    widgets = textual.get("widgets") or []
    if widgets:
        return [(widget["kind"], widget_label(widget)) for widget in widgets]
    slots = item["slots"]
    result: list[tuple[str, str]] = []
    result.extend(("Static", key) for key in slots["copy"])
    result.extend(("Static", key) for key in slots["assets"])
    result.extend(("Static", key) for key in slots.get("fields", []))
    result.extend(("Button", action) for action in slots["actions"])
    return result


def compose_contract_view(view_id: str) -> list[tuple[str, str, str]]:
    item = composition(view_id)
    return [(instance["region"], instance["id"], instance["panel"]) for instance in item["instances"]]


def widget_label(widget: dict) -> str:
    bind = widget["bind"]
    if "copy" in bind:
        return bind["copy"]
    if "asset" in bind:
        return bind["asset"]
    if "action" in bind:
        return bind["action"]
    if "field" in bind:
        return bind["field"]
    return bind.get("literal", widget["id"])
