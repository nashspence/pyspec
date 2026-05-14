from __future__ import annotations

# Generated Textual projection. Do not edit by hand.
# The PM contract owns FSMs/states/actions/widgets/TCSS; a real Textual app imports this file
# and renders FSM state surfaces by id instead of inventing screens, widgets, or action keys.

PROJECT = 'project_dispatch_board'
SCREENS = [{'id': 'screen.fsm.project.board', 'fsm': 'fsm.project.board', 'screen_class': 'ProjectBoardScreen'}]
FSMS = [{'id': 'fsm.project.activity.empty', 'owner_kind': 'fsm', 'owner': 'fsm.project.activity', 'state': 'empty', 'data': [], 'slots': {'copy': ['copy.project.activity.empty.heading', 'copy.project.activity.empty.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'empty', 'transitions': [{'on': 'project.selection_changed', 'from': 'empty', 'to': 'ready'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'on': 'selection.cleared', 'from': 'ready', 'to': 'empty'}], 'context': {'project_id': 'ID'}}}, {'id': 'fsm.project.activity.ready', 'owner_kind': 'fsm', 'owner': 'fsm.project.activity', 'state': 'ready', 'data': [{'query': 'query.project.activity.read', 'capability': 'project.read'}], 'slots': {'copy': ['copy.project.activity.ready.heading'], 'assets': [], 'fields': ['updated_at', 'status', 'assignee'], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'empty', 'transitions': [{'on': 'project.selection_changed', 'from': 'empty', 'to': 'ready'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'on': 'selection.cleared', 'from': 'ready', 'to': 'empty'}], 'context': {'project_id': 'ID'}}}, {'id': 'fsm.project.board.ready', 'owner_kind': 'fsm', 'owner': 'fsm.project.board', 'state': 'ready', 'data': [], 'slots': {'copy': [], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'ready', 'transitions': [], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'fsm.project.detail.error', 'owner_kind': 'fsm', 'owner': 'fsm.project.detail', 'state': 'error', 'data': [], 'slots': {'copy': ['copy.project.detail.error.heading', 'copy.project.detail.error.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'on': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'on': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'fsm.project.detail.loading', 'owner_kind': 'fsm', 'owner': 'fsm.project.detail', 'state': 'loading', 'data': [{'query': 'query.project.detail.read', 'capability': 'project.read'}], 'slots': {'copy': ['copy.project.detail.loading.message'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'on': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'on': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'fsm.project.detail.none', 'owner_kind': 'fsm', 'owner': 'fsm.project.detail', 'state': 'none', 'data': [], 'slots': {'copy': ['copy.project.detail.none.heading', 'copy.project.detail.none.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'on': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'on': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'fsm.project.detail.ready', 'owner_kind': 'fsm', 'owner': 'fsm.project.detail', 'state': 'ready', 'data': [], 'slots': {'copy': ['copy.project.detail.ready.heading'], 'assets': ['asset.project.detail.ready.priority_badge'], 'fields': ['title', 'customer', 'status', 'assignee', 'summary'], 'actions': ['project.approve', 'project.archive']}, 'presentation': {}, 'fsm': {'initial': 'none', 'transitions': [{'on': 'project.selection_changed', 'from': 'none', 'to': 'loading'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'effects': [{'set': {'context': 'project_id', 'value': None}}], 'on': 'selection.cleared', 'from': 'ready', 'to': 'none'}], 'context': {'project_id': 'ID'}}}, {'id': 'fsm.project.list.empty', 'owner_kind': 'fsm', 'owner': 'fsm.project.list', 'state': 'empty', 'data': [], 'slots': {'copy': ['copy.project.list.empty.heading', 'copy.project.list.empty.body'], 'assets': ['asset.project.list.empty.illustration'], 'fields': [], 'actions': ['project.create']}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'on': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'on': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': {'data': {'project_id': '$message.project_id'}, 'message': 'project.selected'}}], 'on': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'fsm.project.list.error', 'owner_kind': 'fsm', 'owner': 'fsm.project.list', 'state': 'error', 'data': [], 'slots': {'copy': ['copy.project.list.error.heading', 'copy.project.list.error.body'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'on': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'on': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': {'data': {'project_id': '$message.project_id'}, 'message': 'project.selected'}}], 'on': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'fsm.project.list.loading', 'owner_kind': 'fsm', 'owner': 'fsm.project.list', 'state': 'loading', 'data': [], 'slots': {'copy': ['copy.project.list.loading.message'], 'assets': [], 'fields': [], 'actions': []}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'on': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'on': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': {'data': {'project_id': '$message.project_id'}, 'message': 'project.selected'}}], 'on': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}, {'id': 'fsm.project.list.ready', 'owner_kind': 'fsm', 'owner': 'fsm.project.list', 'state': 'ready', 'data': [], 'slots': {'copy': ['copy.project.list.ready.heading'], 'assets': [], 'fields': ['title', 'customer', 'priority', 'status'], 'actions': ['project.create', 'project.submit']}, 'presentation': {}, 'fsm': {'initial': 'loading', 'transitions': [{'on': 'data.empty', 'from': 'loading', 'to': 'empty'}, {'on': 'data.ready', 'from': 'loading', 'to': 'ready'}, {'on': 'data.error', 'from': 'loading', 'to': 'error'}, {'on': 'data.ready', 'from': 'empty', 'to': 'ready'}, {'effects': [{'emit': {'data': {'project_id': '$message.project_id'}, 'message': 'project.selected'}}], 'on': 'project.select', 'from': 'ready', 'to': 'ready'}], 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}}}]
COMPOSITIONS = [{'id': 'fsm.project.board.ready', 'fsm': 'fsm.project.board', 'state': 'ready', 'context': {'selected_project_id': 'ID', 'workspace_id': 'ID'}, 'layout': {'html': {'css': {'rules': [{'declarations': {'display': 'grid', 'gap': 'token.gap', 'grid-template-columns': 'token.nav_width 1fr token.aside_width'}, 'selector': 'root'}, {'declarations': {'min-width': 'token.nav_width'}, 'selector': 'region.nav'}, {'declarations': {'min-width': '0'}, 'selector': 'region.main'}, {'declarations': {'min-width': 'token.aside_width'}, 'selector': 'region.aside'}], 'tokens': {'aside_width': '16rem', 'gap': '1rem', 'nav_width': '20rem'}}, 'regions': {'aside': {'classes': ['dispatch-board-aside'], 'element': 'aside', 'order': 3, 'required': True, 'role': 'complementary'}, 'main': {'classes': ['dispatch-board-main'], 'element': 'main', 'order': 2, 'required': True, 'role': 'main'}, 'nav': {'classes': ['dispatch-board-nav'], 'element': 'nav', 'order': 1, 'required': True, 'role': 'navigation'}}, 'root': {'classes': ['dispatch-board'], 'element': 'section', 'role': 'region'}}, 'textual': {'containers': {'aside': {'id': 'aside', 'kind': 'Container', 'order': 3, 'required': True}, 'main': {'id': 'main', 'kind': 'Container', 'order': 2, 'required': True}, 'nav': {'id': 'nav', 'kind': 'Container', 'order': 1, 'required': True}}, 'screen_class': 'ProjectBoardScreen', 'tcss': {'rules': [{'declarations': {'layout': 'horizontal'}, 'selector': 'screen'}, {'declarations': {'width': '32'}, 'selector': 'region.nav'}, {'declarations': {'width': '28'}, 'selector': 'region.aside'}]}}}, 'instances': [{'context': {'selected_project_id': '$fsm.selected_project_id', 'workspace_id': '$fsm.workspace_id'}, 'id': 'list', 'initial': 'loading', 'region': 'nav', 'fsm': 'fsm.project.list'}, {'context': {'project_id': '$fsm.selected_project_id'}, 'id': 'detail', 'initial': 'none', 'region': 'main', 'selected': {'state': 'loading', 'when': {'context_present': 'selected_project_id'}}, 'fsm': 'fsm.project.detail'}, {'context': {'project_id': '$fsm.selected_project_id'}, 'id': 'activity', 'initial': 'empty', 'region': 'aside', 'selected': {'state': 'ready', 'when': {'context_present': 'selected_project_id'}}, 'fsm': 'fsm.project.activity'}], 'sync': [{'do': [{'set': {'context': 'selected_project_id', 'from': '$message.project_id'}}, {'send': {'data': {'project_id': '$message.project_id'}, 'message': 'project.selection_changed', 'instance': 'detail'}}, {'send': {'data': {'project_id': '$message.project_id'}, 'message': 'project.selection_changed', 'instance': 'activity'}}], 'id': 'select_project_updates_fsms', 'when': {'instance': 'list', 'message': 'project.selected'}}]}]
TCSS = '/* Generated Textual CSS contract. Do not edit. */\nScreen {\n  layout: vertical;\n}\n.contract-fsm-surface {\n  padding: 1;\n}\nProjectBoardScreen {\n  layout: horizontal;\n}\n#nav {\n  width: 32;\n}\n#aside {\n  width: 28;\n}\n'


def fsm_surface(surface_id: str) -> dict:
    for item in FSMS:
        if item["id"] == surface_id:
            return item
    raise KeyError(surface_id)


def composition(composition_id: str) -> dict:
    for item in COMPOSITIONS:
        if item["id"] == composition_id:
            return item
    raise KeyError(composition_id)


def textual_css() -> str:
    return TCSS


def compose_contract_fsm(surface_id: str) -> list[tuple[str, str]]:
    item = fsm_surface(surface_id)
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


def compose_contract_composition(composition_id: str) -> list[tuple[str, str, str]]:
    item = composition(composition_id)
    return [(instance["region"], instance["id"], instance["fsm"]) for instance in item["instances"]]


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
