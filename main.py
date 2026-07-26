import sys
import traceback
from pathlib import Path


def main() -> int:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont, QColor, QPalette
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from controllers.main_controller import MainController
    except ModuleNotFoundError as exc:
        print(f"Missing package: {exc.name}", file=sys.stderr)
        print("Run RUN_LAPTOP_HEALTH_MONITOR.bat to install the supported dependencies.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Startup import error: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("Laptop Health Monitor")
    app.setOrganizationName("Laptop Health Monitor")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    # Force a consistent light palette even when Windows is using dark mode.
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f7fb"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f8fafc"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ef4444"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2563eb"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94a3b8"))
    app.setPalette(palette)
    app.setStyleSheet("QMenuBar, QMenu, QMessageBox, QFileDialog { background:#ffffff; color:#0f172a; }")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    try:
        window = MainController()
        app.aboutToQuit.connect(window.cleanup)
        window.show()
        return int(app.exec())
    except Exception as exc:
        traceback.print_exc()
        QMessageBox.critical(None, "Laptop Health Monitor", f"The application could not start:\n\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
