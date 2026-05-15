from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static

LINES = [('static', 'No dispatch projects yet'), ('static', 'Create the first project to start coordinating work for this workspace.'), ('static', 'Empty dispatch queue illustration'), ('button', 'Operation Project Create')]


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
