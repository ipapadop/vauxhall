"""UI components for the Vauxhall Agent Dashboard."""

import tkinter as tk
from tkinter import ttk

import pyperclip


class AgentCard(ttk.Frame):
    """Widget representing a single agent's status and activity."""

    def __init__(self, parent: tk.Widget, agent: str, workspace: str) -> None:
        """Initialize the agent card.

        Args:
            parent: Parent widget.
            agent: Agent name/ID.
            workspace: Workspace directory path.
        """
        super().__init__(parent, padding=10, style="Card.TFrame")
        self.agent = agent
        self.workspace = workspace

        self.header = ttk.Label(
            self, text=f"{agent} @ {workspace}", font=("Arial", 10, "bold")
        )
        self.header.pack(fill="x")

        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(self, textvariable=self.status_var)
        self.status_label.pack(fill="x")

        self.log_text = tk.Text(
            self, height=3, state="disabled", bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log_text.pack(fill="x", pady=5)

        self.bind("<Button-1>", self._on_click)

    def update_data(self, data: dict) -> None:
        """Update the card with new agent activity data.

        Args:
            data: Dictionary containing agent state and activity details.
        """
        self.status_var.set(data.get("state", "Unknown"))
        details = data.get("details", {})
        if "tool" in details:
            self._update_log(f"Running: {details['tool']}\n{details.get('cmd', '')}")
        if data.get("state") == "Error":
            self.configure(style="Error.TFrame")

    def _update_log(self, text: str) -> None:
        """Update the activity log text area."""
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", text)
        self.log_text.config(state="disabled")

    def _on_click(self, event: tk.Event) -> None:
        """Handle click event to copy workspace path to clipboard."""
        pyperclip.copy(f"cd {self.workspace}")
        print(f"Copied to clipboard: cd {self.workspace}")
