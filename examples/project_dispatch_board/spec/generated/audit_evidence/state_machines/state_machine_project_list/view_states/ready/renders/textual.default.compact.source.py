from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static

LINES = [('static', 'Dispatch queue'), ('static', 'Title: Inspect loading dock sensor'), ('static', 'Customer: Harbor Logistics'), ('static', 'Priority: Normal'), ('static', 'Status: draft'), ('static', 'Title: Replace rooftop condenser fan'), ('static', 'Customer: Atlas Foods'), ('static', 'Priority: High'), ('static', 'Status: submitted'), ('button', 'Operation Project Create'), ('button', 'Operation Project Submit')]


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
