import os
from pyloid import Pyloid
from vauxhall.dashboard.ipc import DashboardIPC

def main():
    app = Pyloid(app_name="Vauxhall Dashboard")
    
    # Create window with IPC
    window = app.create_window(
        title="Vauxhall Agent Dashboard",
        width=1000,
        height=800,
        IPCs=[DashboardIPC()]
    )
    
    # Path to UI files
    ui_dir = os.path.join(os.path.dirname(__file__), "ui")
    index_path = os.path.join(ui_dir, "index.html")
    
    # Ensure UI dir exists
    os.makedirs(ui_dir, exist_ok=True)
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            f.write("<h1>Vauxhall Loading...</h1>")

    window.load_file(index_path)
    window.show_and_focus()
    app.run()

if __name__ == "__main__":
    main()
