from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static

LINES = [('static', 'Dispatch queue'), ('static', 'Title: Replace rooftop condenser fan'), ('static', 'Customer: Atlas Foods'), ('static', 'Priority: High'), ('static', 'Status: submitted'), ('static', 'Title: Inspect loading dock sensor'), ('static', 'Customer: Harbor Logistics'), ('static', 'Priority: Normal'), ('static', 'Status: draft'), ('button', 'Create'), ('button', 'Submit'), ('static', 'Replace rooftop condenser fan · Atlas Foods'), ('static', 'High priority'), ('static', 'Title: Replace rooftop condenser fan'), ('static', 'Customer: Atlas Foods'), ('static', 'Status: submitted'), ('static', 'Assignee: Maya Chen'), ('static', 'Summary: Technician needs approval before ordering the replacement fan motor.'), ('static', 'Title: Inspect loading dock sensor'), ('static', 'Customer: Harbor Logistics'), ('static', 'Status: draft'), ('static', 'Assignee: Unassigned'), ('static', 'Summary: Customer reports intermittent alerts from dock door 3.'), ('button', 'Approve'), ('button', 'Archive'), ('static', 'Latest activity'), ('static', 'Updated At: 2026-05-11T08:45:00Z'), ('static', 'Status: submitted'), ('static', 'Assignee: Maya Chen'), ('static', 'Updated At: 2026-05-11T07:15:00Z'), ('static', 'Status: draft'), ('static', 'Assignee: Unassigned')]


class AuditApp(App[None]):
    CSS = """
    Screen { layout: vertical; }
    #root { padding: 1; }
    Static { margin: 0 0 1 0; }
    Button { margin: 0 0 1 0; width: auto; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            for index, (kind, value) in enumerate(LINES):
                if kind == "button":
                    yield Button(value, id=f"button_{index}")
                else:
                    yield Static(value, id=f"line_{index}")


if __name__ == "__main__":
    AuditApp().run()
