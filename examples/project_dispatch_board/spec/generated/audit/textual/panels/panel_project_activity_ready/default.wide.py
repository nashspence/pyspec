from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static

LINES = [('static', 'Latest activity'), ('static', 'Updated At: 2026-05-11T08:45:00Z'), ('static', 'Status: submitted'), ('static', 'Assignee: Maya Chen')]


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
