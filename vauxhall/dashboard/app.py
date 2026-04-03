import tkinter as tk
from tkinter import ttk

from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.dashboard.ui_components import AgentCard


class VauxhallApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vauxhall Agent Dashboard")
        self.geometry("600x800")

        self.cards = {}  # (agent, workspace) -> AgentCard

        self.scroll_canvas = tk.Canvas(self)
        self.scroll_frame = ttk.Frame(self.scroll_canvas)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.scroll_canvas.yview
        )
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scroll_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        # Ensure scrollable area updates
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.configure(
                scrollregion=self.scroll_canvas.bbox("all")
            ),
        )

        self.mqtt = DashboardSubscriber(self._on_telemetry)
        self.mqtt.start()

    def _on_telemetry(self, data):
        key = (data["agent"], data["workspace"])
        if key not in self.cards:
            card = AgentCard(self.scroll_frame, data["agent"], data["workspace"])
            card.pack(fill="x", padx=10, pady=5)
            self.cards[key] = card

        self.cards[key].update_data(data)


if __name__ == "__main__":
    app = VauxhallApp()
    app.mainloop()
