import csv
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets
from utils.system_probe import SystemProbe
from ai.predictor import BatteryRULPredictor


BLUE = "#2563eb"
GREEN = "#16a34a"
ORANGE = "#f59e0b"
RED = "#ef4444"
PURPLE = "#7c3aed"
PINK = "#ec4899"
TEXT = "#0f172a"
MUTED = "#475569"
BORDER = "#dbe5f2"
BG = "#f5f7fb"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


class ProgressRing(QtWidgets.QWidget):
    def __init__(self, value=0, color=BLUE, suffix="%", parent=None):
        super().__init__(parent)
        self.value = float(value)
        self.color = QtGui.QColor(color)
        self.suffix = suffix
        self.setMinimumSize(120, 120)

    def setValue(self, value):
        self.value = max(0, min(100, safe_float(value)))
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(14, 14, -14, -14)

        pen_bg = QtGui.QPen(QtGui.QColor("#e5e7eb"), 10)
        pen_bg.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 210 * 16, -240 * 16)

        pen = QtGui.QPen(self.color, 10)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 210 * 16, int(-240 * 16 * self.value / 100))

        painter.setPen(QtGui.QColor(TEXT))
        font = painter.font()
        font.setPointSize(22)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, f"{int(self.value)}")

        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(MUTED))
        painter.drawText(rect.adjusted(0, 42, 0, 42), QtCore.Qt.AlignmentFlag.AlignCenter, self.suffix)


class Card(QtWidgets.QFrame):
    """Modern elevated surface used consistently across the desktop UI."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QtGui.QColor(15, 23, 42, 16))
        self.setGraphicsEffect(shadow)


class MainController(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Laptop Health Monitor - Real Time")
        self.resize(1366, 768)
        self.setMinimumSize(1060, 660)

        self.metrics_history: list[dict[str, Any]] = []
        self.probe = SystemProbe()
        self.research_predictor = BatteryRULPredictor()
        self.system_inventory = self.probe.static_snapshot()
        self.current_metrics: dict[str, float] = {}
        self.last_updated_labels: list[QtWidgets.QLabel] = []
        self.action_log: list[str] = []
        self.active_recommendation_filter = "All Recommendations"
        self.temp_scan_result = {"files": 0, "bytes": 0}
        self.reports_dir = Path.cwd() / "reports"
        self.reports_dir.mkdir(exist_ok=True)

        # RUL state used only by the AI Prediction page.
        self._rul_smoothed_years: float | None = None
        self._rul_last_update = time.monotonic()
        self._rul_hardware_cache: dict[str, float | None] = {}
        self._rul_hardware_cache_at = 0.0

        # Defaults required before UI construction because Recommendations page
        # is populated while _build_ui() is still running.
        self.temp_warning_value = 80
        self.temp_critical_value = 90
        self.monitor_interval_value = 3

        self.setStyleSheet(self._style())
        self._build_ui()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.refresh_all)
        self._timer.start(3000)
        self.refresh_all()

    def cleanup(self):
        try:
            self._timer.stop()
        except Exception:
            pass

    def _style(self):
        return f"""
        QMainWindow {{ background: #f8fafc; }}
        QWidget {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 12px; color: {TEXT}; }}
        QToolTip {{ background: #0f172a; color: white; border: 0; padding: 6px 9px; }}

        #appHeader {{ background: #ffffff; border-bottom: 1px solid #dfe7f1; }}
        #logoBadge {{ background: #eff6ff; color: #1473e6; border: 1px solid #bfdbfe; border-radius: 11px; font-size: 20px; font-weight: 900; }}
        #brandTitle {{ font-size: 17px; font-weight: 800; color: #0768d7; }}
        #brandSub {{ font-size: 9px; color: #475569; }}
        #lastUpdated {{ color: #475569; font-size: 9px; }}

        #sidebar {{ background: #ffffff; border-right: 1px solid #e3e9f1; }}
        QListWidget {{ border: none; background: transparent; outline: 0; padding: 8px 7px; }}
        QListWidget::item {{ height: 36px; border-radius: 7px; padding-left: 8px; margin: 2px 0; color: #334155; font-size: 10px; }}
        QListWidget::item:hover {{ background: #f1f5f9; color: #0b69d8; }}
        QListWidget::item:selected {{ background: #0877e8; color: #ffffff; font-weight: 700; }}

        #pageTitle {{ font-size: 15px; font-weight: 800; color: #111827; }}
        #pageSubtitle {{ color: #64748b; font-size: 9px; }}
        #card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }}
        #metricCard {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }}
        #cardTitle {{ font-size: 10px; font-weight: 700; color: #334155; }}
        #cardValue {{ font-size: 22px; font-weight: 800; color: #0f172a; }}
        #sectionHeader {{ font-size: 11px; font-weight: 800; color: #111827; }}
        #appFooter {{ background: #ffffff; border-top: 1px solid #e3e9f1; color: #15803d; font-size: 9px; }}

        QPushButton {{ background: #ffffff; color: #1269cf; border: 1px solid #c7d7eb; border-radius: 7px; padding: 5px 9px; font-weight: 700; min-height: 17px; font-size: 10px; }}
        QPushButton:hover {{ background: #eff6ff; border-color: #60a5fa; }}
        QPushButton#primaryAction {{ background: #0877e8; color: white; border-color: #0877e8; }}
        QPushButton#primaryAction:hover {{ background: #0668ce; }}
        QPushButton#dangerAction {{ background: #fff7ed; color: #c2410c; border-color: #fed7aa; }}

        QLineEdit, QComboBox, QSpinBox {{ background: white; border: 1px solid #d8e0eb; border-radius: 4px; padding: 5px 8px; selection-background-color: #dbeafe; font-size: 10px; }}
        QCheckBox {{ spacing: 7px; font-size: 10px; }}
        QTableWidget {{ background: white; alternate-background-color: #fafcff; border: 1px solid #dfe6ee; border-radius: 4px; gridline-color: #edf2f7; selection-background-color: #e8f0ff; selection-color: #0f172a; outline: 0; font-size: 10px; }}
        QTableWidget::item {{ padding: 5px; border-bottom: 1px solid #eef2f7; }}
        QHeaderView::section {{ background: #f3f4f6; color: #334155; padding: 6px; border: none; border-bottom: 1px solid #dde3ea; font-weight: 700; font-size: 10px; }}
        QProgressBar {{ background: #e8edf4; border: none; border-radius: 4px; height: 8px; text-align: center; }}
        QProgressBar::chunk {{ background: #1684ee; border-radius: 4px; }}

        #uninstallTabBar {{ background: transparent; border-bottom: 1px solid #e2e8f0; }}
        QPushButton#uninstallTab {{ background: transparent; border: none; border-radius: 0; color: #334155; padding: 10px 14px; font-size: 11px; }}
        QPushButton#uninstallTab:checked {{ color: #2563eb; border-bottom: 3px solid #2563eb; font-weight: 800; }}
        QPushButton#tableAction {{ background: #ffffff; color: #2563eb; border: 1px solid #bfdbfe; min-width: 78px; }}
        QPushButton#tableAction:hover {{ background: #eff6ff; }}
        QToolButton#moreAction {{ background: #ffffff; border: 1px solid #dbe5f2; border-radius: 6px; min-width: 28px; min-height: 26px; }}
        QLabel#usageGreen {{ background: #ecfdf5; color: #15803d; border-radius: 5px; padding: 3px 8px; font-weight: 700; }}
        QLabel#usageAmber {{ background: #fffbeb; color: #b45309; border-radius: 5px; padding: 3px 8px; font-weight: 700; }}
        QLabel#usageRed {{ background: #fef2f2; color: #b91c1c; border-radius: 5px; padding: 3px 8px; font-weight: 700; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 1px; }}
        QScrollBar::handle:vertical {{ background: #cbd5e1; min-height: 24px; border-radius: 4px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QtWidgets.QFrame()
        header.setObjectName("appHeader")
        header.setFixedHeight(64)
        hl = QtWidgets.QHBoxLayout(header)
        hl.setContentsMargins(14, 8, 14, 8)
        hl.setSpacing(10)
        logo = QtWidgets.QLabel("◇")
        logo.setObjectName("logoBadge")
        logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(38, 38)
        hl.addWidget(logo)
        bt = QtWidgets.QVBoxLayout(); bt.setSpacing(0)
        title = QtWidgets.QLabel("Laptop Health Monitor"); title.setObjectName("brandTitle")
        sub = QtWidgets.QLabel("Real-time Monitoring & Predictive Maintenance System"); sub.setObjectName("brandSub")
        bt.addWidget(title); bt.addWidget(sub)
        hl.addLayout(bt)
        hl.addStretch()
        self.global_last_updated = QtWidgets.QLabel("Last Updated: --")
        self.global_last_updated.setObjectName("lastUpdated")
        self.last_updated_labels.append(self.global_last_updated)
        hl.addWidget(self.global_last_updated)
        refresh = QtWidgets.QPushButton("⟳  Refresh")
        refresh.clicked.connect(self.action_refresh)
        hl.addWidget(refresh)
        root_layout.addWidget(header)

        body = QtWidgets.QWidget()
        body.setObjectName("appBody")
        body_layout = QtWidgets.QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        sidebar = QtWidgets.QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(148)
        sb = QtWidgets.QVBoxLayout(sidebar); sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(0)
        self.nav = QtWidgets.QListWidget(); self.nav.setSpacing(0)
        self.nav.addItems([
            "⌂  Dashboard", "◉  Monitor", "♨  Temperature", "⌁  RUL Prediction",
            "◇  Health History", "✦  Recommendations", "▣  Storage Manager", "▦  Smart Uninstaller",
            "▦  System Data", "▤  Reports", "⚙  Settings", "ⓘ  About",
        ])
        self.nav.currentRowChanged.connect(self.switch_page)
        sb.addWidget(self.nav, 1)
        body_layout.addWidget(sidebar)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setObjectName("pageStack")
        body_layout.addWidget(self.stack, 1)
        for page in [
            self.create_dashboard_page(), self.create_monitoring_page(), self.create_thermal_page(),
            self.create_ai_page(), self.create_health_history_page(), self.create_recommendations_page(),
            self.create_storage_page(), self.create_uninstaller_page(), self.create_system_data_page(), self.create_reports_page(), self.create_settings_page(),
            self.create_about_page(),
        ]:
            self.stack.addWidget(self._scroll_page(page))
        root_layout.addWidget(body, 1)

        footer = QtWidgets.QFrame(); footer.setObjectName("appFooter"); footer.setFixedHeight(24)
        fl = QtWidgets.QHBoxLayout(footer); fl.setContentsMargins(10, 2, 10, 2)
        self.footer_status = QtWidgets.QLabel("●  System Status: All systems operational")
        self.side_health_value = QtWidgets.QLabel()
        self.side_health_value.hide()
        fl.addWidget(self.footer_status); fl.addStretch()
        root_layout.addWidget(footer)
        self.nav.setCurrentRow(0)

    def _scroll_page(self, page):
        """Wrap every page in a responsive scroll area so controls never overlap or clip."""
        page.setObjectName("pageSurface")
        page.setMinimumWidth(760)
        page.setAutoFillBackground(True)
        palette = page.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(BG))
        page.setPalette(palette)
        area = QtWidgets.QScrollArea()
        area.setObjectName("pageScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.viewport().setAutoFillBackground(True)
        vp = area.viewport().palette()
        vp.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(BG))
        area.viewport().setPalette(vp)
        area.setWidget(page)
        return area

    def _side_status_card(self, title, value, desc):
        card = QtWidgets.QFrame()
        card.setObjectName("sideStatus")
        card.setFixedHeight(94)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(2)
        t = QtWidgets.QLabel(title)
        t.setStyleSheet("font-size:9px;font-weight:800;color:#94a3b8;")
        layout.addWidget(t)
        self.side_health_value = QtWidgets.QLabel("●  " + value)
        self.side_health_value.setStyleSheet(f"font-size:15px;font-weight:800;color:{GREEN};")
        layout.addWidget(self.side_health_value)
        d = QtWidgets.QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet("font-size:10px;color:#64748b;")
        layout.addWidget(d)
        return card

    def page_shell(self, title, subtitle):
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)
        header = QtWidgets.QVBoxLayout(); header.setSpacing(0)
        t = QtWidgets.QLabel(title); t.setObjectName("pageTitle")
        s = QtWidgets.QLabel(subtitle); s.setObjectName("pageSubtitle")
        header.addWidget(t); header.addWidget(s)
        outer.addLayout(header)
        return page, outer

    def metric_card(self, title, value, status, color, icon="", explanation=""):
        card = Card()
        card.setObjectName("metricCard")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        top = QtWidgets.QHBoxLayout()
        title_l = QtWidgets.QLabel(title)
        title_l.setObjectName("cardTitle")
        top.addWidget(title_l)
        top.addStretch()
        ic = QtWidgets.QLabel(icon)
        ic.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        ic.setFixedSize(23, 23)
        ic.setStyleSheet(f"background:{color}18;color:{color};border-radius:6px;font-size:12px;font-weight:800;")
        top.addWidget(ic)
        layout.addLayout(top)
        val_l = QtWidgets.QLabel(value)
        val_l.setObjectName("cardValue")
        layout.addWidget(val_l)
        status_l = QtWidgets.QLabel(status)
        status_l.setStyleSheet(f"font-size:11px;font-weight:700;color:{color};")
        layout.addWidget(status_l)
        exp_l = QtWidgets.QLabel(explanation)
        exp_l.setWordWrap(True)
        exp_l.setStyleSheet("color:#94a3b8;font-size:10px;")
        layout.addWidget(exp_l)
        return card, val_l, status_l, exp_l

    def create_dashboard_page(self):
        page, outer = self.page_shell("Dashboard", "Real-time system health and predictive maintenance overview")
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.metric_widgets = {}
        specs = [
            ("Overall Health", "health_score", "/100", GREEN, "✓", "Combined health score"),
            ("CPU Usage", "cpu_usage", "%", BLUE, "CPU", "Processor utilization"),
            ("RAM Usage", "ram_usage", "%", PURPLE, "RAM", "Memory utilization"),
            ("Battery", "battery_health", "%", GREEN, "▯", "Charge level"),
            ("Temperature", "temperature", "°C", ORANGE, "♨", "Sensor or estimate"),
            ("Disk Usage", "disk_usage", "%", BLUE, "◔", "System drive used"),
        ]
        for i, (title, key, suffix, color, icon, explanation) in enumerate(specs):
            card, val, status, exp = self.metric_card(title, "--", "Checking", color, icon, explanation)
            card.setMinimumHeight(112)
            card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            grid.addWidget(card, i // 4, i % 4)
            self.metric_widgets[key] = (val, status, suffix, exp)
        uptime_card, self.dashboard_uptime_value, _, _ = self.metric_card("Uptime", "--", "Active", GREEN, "◷", "Since last restart")
        rul_card, self.dashboard_rul_value, _, _ = self.metric_card("Predicted RUL", "--", "Condition-based", BLUE, "AI", "Academic estimate")
        self.dashboard_uptime_value.setStyleSheet("font-size:22px;font-weight:800;color:#0f172a;")
        self.dashboard_rul_value.setStyleSheet("font-size:20px;font-weight:800;color:#0f172a;")
        self.dashboard_rul_value.setWordWrap(True)
        uptime_card.setMinimumHeight(112); rul_card.setMinimumHeight(112)
        uptime_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        rul_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        grid.addWidget(uptime_card, 1, 2); grid.addWidget(rul_card, 1, 3)
        for col in range(4): grid.setColumnStretch(col, 1)
        outer.addLayout(grid)

        body = QtWidgets.QHBoxLayout(); body.setSpacing(12)
        graph_card = Card(); gl = QtWidgets.QVBoxLayout(graph_card); gl.setContentsMargins(14, 12, 14, 12)
        head = QtWidgets.QHBoxLayout()
        h = QtWidgets.QLabel("System Health Trend"); h.setObjectName("sectionHeader")
        legend = QtWidgets.QLabel("CPU  •  RAM  •  Temperature"); legend.setStyleSheet("color:#64748b;font-size:10px;")
        head.addWidget(h); head.addStretch(); head.addWidget(legend); gl.addLayout(head)
        self.dashboard_graph = pg.PlotWidget(); self.dashboard_graph.setMinimumHeight(205)
        self.dashboard_graph.setBackground("white"); self.dashboard_graph.showGrid(x=True, y=True, alpha=0.14)
        self.dashboard_graph.setYRange(0, 100); self.dashboard_graph.setLabel("left", "Usage (%) / Temperature (°C)"); self.dashboard_graph.setLabel("bottom", "Recent samples")
        self.dashboard_graph.getAxis('left').setTextPen('#64748b'); self.dashboard_graph.getAxis('bottom').setTextPen('#64748b')
        self.dashboard_graph.addLegend(offset=(-12, 10), labelTextColor="#334155", brush=pg.mkBrush(255, 255, 255, 225), pen=pg.mkPen("#e2e8f0"))
        gl.addWidget(self.dashboard_graph); body.addWidget(graph_card, 7)

        risk_card = Card(); rl = QtWidgets.QVBoxLayout(risk_card); rl.setContentsMargins(14, 12, 14, 12); rl.setSpacing(7)
        rh = QtWidgets.QLabel("Component Risk"); rh.setObjectName("sectionHeader"); rl.addWidget(rh)
        self.dashboard_risk_labels = {}
        for name in ["Battery", "Temperature", "CPU", "RAM", "Storage"]:
            row = QtWidgets.QHBoxLayout(); label = QtWidgets.QLabel(name); label.setStyleSheet("color:#475569;")
            status = QtWidgets.QLabel("Checking"); status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight); status.setStyleSheet("font-size:11px;font-weight:800;color:#64748b;")
            row.addWidget(label); row.addStretch(); row.addWidget(status); rl.addLayout(row); self.dashboard_risk_labels[name] = status
        rl.addStretch()
        scan = QtWidgets.QPushButton("Run Smart Scan"); scan.setObjectName("primaryAction"); scan.clicked.connect(self.action_smart_scan); rl.addWidget(scan)
        self.quick_action_status = QtWidgets.QLabel("Monitoring active. Safe actions require confirmation."); self.quick_action_status.setWordWrap(True); self.quick_action_status.setStyleSheet("color:#64748b;font-size:10px;")
        rl.addWidget(self.quick_action_status); body.addWidget(risk_card, 3)
        outer.addLayout(body, 1)
        return page

    def create_monitoring_page(self):
        page, outer = self.page_shell("Monitor", "Detailed live system metrics and performance history")
        self.monitor_metric_values = {}
        metrics_grid = QtWidgets.QGridLayout()
        metrics_grid.setSpacing(12)
        specs = [
            ("CPU Usage", "cpu_usage", "%", BLUE),
            ("RAM Usage", "ram_usage", "%", PURPLE),
            ("Swap Usage", "swap", "%", ORANGE),
            ("Disk Usage", "disk_usage", "%", BLUE),
            ("Battery Level", "battery_health", "%", GREEN),
            ("Temperature", "temperature", "°C", ORANGE),
            ("CPU Frequency", "cpu_frequency", " GHz", BLUE),
            ("Uptime", "uptime", "", GREEN),
        ]
        for i, (title, key, suffix, color) in enumerate(specs):
            card = Card()
            card.setMinimumHeight(92)
            layout = QtWidgets.QVBoxLayout(card)
            title_label = QtWidgets.QLabel(title)
            title_label.setObjectName("cardTitle")
            value_label = QtWidgets.QLabel("--")
            value_label.setStyleSheet(f"font-size:24px;font-weight:900;color:{color};")
            layout.addWidget(title_label)
            layout.addWidget(value_label)
            metrics_grid.addWidget(card, i // 4, i % 4)
            metrics_grid.setColumnStretch(i % 4, 1)
            self.monitor_metric_values[key] = (value_label, suffix)
        outer.addLayout(metrics_grid)

        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        title = QtWidgets.QLabel("Live CPU, RAM and Temperature History")
        title.setObjectName("sectionHeader")
        l.addWidget(title)
        self.monitoring_graph = pg.PlotWidget()
        self.monitoring_graph.setMinimumHeight(270)
        self.monitoring_graph.setBackground("white")
        self.monitoring_graph.showGrid(x=True, y=True, alpha=0.18)
        self.monitoring_graph.setYRange(0, 100)
        self.monitoring_graph.setLabel("left", "Usage (%) / Temperature (°C)")
        self.monitoring_graph.setLabel("bottom", "Monitoring samples")
        self.monitoring_graph.addLegend(offset=(-12, 10), labelTextColor="#334155", brush=pg.mkBrush(255, 255, 255, 225), pen=pg.mkPen("#e2e8f0"))
        l.addWidget(self.monitoring_graph)
        outer.addWidget(card, 1)
        return page

    def create_thermal_page(self):
        page, outer = self.page_shell("Temperature Monitoring", "Real-time and historical temperature data")
        card = Card()
        l = QtWidgets.QHBoxLayout(card)

        self.thermal_status = QtWidgets.QLabel("Checking")
        self.thermal_status.setStyleSheet(f"font-size:30px;font-weight:900;color:{ORANGE};")
        self.thermal_temp = QtWidgets.QLabel("--°C")
        self.thermal_temp.setStyleSheet("font-size:46px;font-weight:900;")
        self.thermal_message = QtWidgets.QLabel("Temperature sensor support depends on hardware and OS.")
        self.thermal_message.setWordWrap(True)
        self.thermal_message.setStyleSheet(f"color:{MUTED};")

        col = QtWidgets.QVBoxLayout()
        col.addWidget(QtWidgets.QLabel("Thermal Status"))
        col.addWidget(self.thermal_status)
        col.addWidget(self.thermal_temp)
        col.addWidget(self.thermal_message)
        l.addLayout(col)

        self.thermal_ring = ProgressRing(62, ORANGE, "°C")
        l.addWidget(self.thermal_ring)
        outer.addWidget(card)

        self.thermal_graph = pg.PlotWidget()
        self.thermal_graph.setBackground("white")
        self.thermal_graph.showGrid(x=True, y=True, alpha=0.18)
        self.thermal_graph.setLabel("left", "Temperature (°C)")
        self.thermal_graph.setLabel("bottom", "Monitoring samples")
        self.thermal_graph.addLegend(offset=(-12, 10), labelTextColor="#334155", brush=pg.mkBrush(255, 255, 255, 225), pen=pg.mkPen("#e2e8f0"))
        gcard = Card()
        gl = QtWidgets.QVBoxLayout(gcard)
        gl.addWidget(QtWidgets.QLabel("Temperature History"))
        gl.addWidget(self.thermal_graph)
        outer.addWidget(gcard, 1)
        return page

    def create_storage_page(self):
        page, outer = self.page_shell("Storage Manager", "Analyze disk usage and manage temporary files safely")
        self.drive_cards = QtWidgets.QHBoxLayout()
        outer.addLayout(self.drive_cards)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.storage_breakdown_card())
        row.addWidget(self.info_big_card("Temp Junk Scan", "0 MB", "Run scan to calculate temp junk", "Scan Temp Junk", self.action_scan_junk, "junk"))
        row.addWidget(self.info_big_card("Large Files", "Open Tool", "Open File Explorer search for large files", "Open Large File Search", self.action_manage_large_files, "large"))
        outer.addLayout(row)

        health = Card()
        hl = QtWidgets.QHBoxLayout(health)
        hl.addWidget(QtWidgets.QLabel("✓  Storage Health Overview"))
        self.storage_health_label = QtWidgets.QLabel("Good")
        self.storage_health_label.setStyleSheet(f"font-size:24px;font-weight:900;color:{GREEN};")
        hl.addWidget(self.storage_health_label)
        hl.addStretch()
        self.storage_health_details = QtWidgets.QLabel("Drive details update in real time.")
        hl.addWidget(self.storage_health_details)
        outer.addWidget(health)
        return page

    def drive_card(self, name, used, total, free, color):
        card = Card()
        l = QtWidgets.QHBoxLayout(card)
        ring = ProgressRing(used, color, "Used")
        l.addWidget(ring)

        col = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel(name)
        title.setObjectName("sectionHeader")
        col.addWidget(title)
        for k, v in [("Total Size", total), ("Used Space", f"{used}%"), ("Free Space", free), ("File System", "Detected")]:
            col.addWidget(QtWidgets.QLabel(f"{k}:  {v}"))

        btn = QtWidgets.QPushButton("View Details")
        btn.clicked.connect(lambda checked=False, n=name, u=used, t=total, f=free: self.action_drive_details(n, u, t, f))
        col.addWidget(btn)
        l.addLayout(col)
        return card

    def storage_breakdown_card(self):
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        h = QtWidgets.QLabel("System Drive Usage")
        h.setObjectName("sectionHeader")
        l.addWidget(h)
        self.storage_progress = QtWidgets.QProgressBar()
        self.storage_progress.setValue(0)
        self.storage_progress.setTextVisible(True)
        self.storage_progress.setFixedHeight(18)
        l.addWidget(self.storage_progress)
        self.storage_breakdown_text = QtWidgets.QLabel("Drive usage updates automatically.")
        self.storage_breakdown_text.setWordWrap(True)
        self.storage_breakdown_text.setStyleSheet(f"color:{MUTED};")
        l.addWidget(self.storage_breakdown_text)
        l.addStretch()
        btn = QtWidgets.QPushButton("Open System Drive")
        btn.clicked.connect(self.action_open_system_drive)
        l.addWidget(btn)
        return card

    def info_big_card(self, title, value, desc, button, slot, kind):
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        h = QtWidgets.QLabel(title)
        h.setObjectName("sectionHeader")
        l.addWidget(h)
        v = QtWidgets.QLabel(value)
        v.setStyleSheet("font-size:32px;font-weight:900;")
        l.addWidget(v, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        d = QtWidgets.QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{MUTED};")
        l.addWidget(d, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        if kind == "junk":
            self.junk_value_label = v
            self.junk_desc_label = d
            v.setStyleSheet("font-size:36px;font-weight:900;color:#0f172a;")
            d.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            d.setMinimumHeight(42)
            l.addStretch()
            actions = QtWidgets.QVBoxLayout()
            actions.setSpacing(8)
            btn = QtWidgets.QPushButton("Scan Temp Junk")
            btn.setObjectName("primaryAction")
            btn.setMinimumHeight(42)
            btn.clicked.connect(slot)
            actions.addWidget(btn)
            clean = QtWidgets.QPushButton("Clean Scanned Junk")
            clean.setObjectName("dangerAction")
            clean.setMinimumHeight(42)
            clean.clicked.connect(self.action_clean_junk)
            actions.addWidget(clean)
            l.addLayout(actions)
            return card
        l.addStretch()
        btn = QtWidgets.QPushButton(button)
        btn.setObjectName("primaryAction")
        btn.setMinimumHeight(42)
        btn.clicked.connect(slot)
        l.addWidget(btn)
        return card

    def create_uninstaller_page(self):
        page, outer = self.page_shell(
            "Smart Uninstaller",
            "Review installed software, search and sort programs, and launch the official Windows uninstall workflow safely.",
        )
        outer.setSpacing(14)

        tab_bar = QtWidgets.QFrame(); tab_bar.setObjectName("uninstallTabBar")
        tab_layout = QtWidgets.QHBoxLayout(tab_bar); tab_layout.setContentsMargins(8, 0, 8, 0); tab_layout.setSpacing(12)
        self.uninstaller_tab_group = QtWidgets.QButtonGroup(self); self.uninstaller_tab_group.setExclusive(True)
        self.uninstaller_tabs = {}
        for i, text in enumerate(("Installed Programs", "Windows Apps", "Residual Files")):
            btn = QtWidgets.QPushButton(text); btn.setObjectName("uninstallTab"); btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, name=text: self.action_uninstaller_tab(name))
            self.uninstaller_tab_group.addButton(btn, i); self.uninstaller_tabs[text] = btn; tab_layout.addWidget(btn)
        self.uninstaller_tabs["Installed Programs"].setChecked(True)
        tab_layout.addStretch(); outer.addWidget(tab_bar)

        stats = QtWidgets.QHBoxLayout(); stats.setSpacing(12)
        self.program_count_card = self.smart_stat_card("▦", "Total Programs", "0", "Installed on your system", "#2563eb", "program_total_value")
        self.frequent_card = self.smart_stat_card("◉", "Recently Installed", "0", "Installed within 90 days", "#16a34a", "program_recent_value")
        self.rare_card = self.smart_stat_card("⌛", "Older Programs", "0", "Installed more than one year ago", "#f59e0b", "program_old_value")
        self.large_card = self.smart_stat_card("▣", "Large Programs", "0", "Using at least 500 MB", "#ef4444", "program_large_value")
        self.space_card = self.smart_stat_card("◷", "Space Used", "0 GB", "Reported by installed programs", "#7c3aed", "program_space_value")
        for card in (self.program_count_card, self.frequent_card, self.rare_card, self.large_card, self.space_card): stats.addWidget(card, 1)
        outer.addLayout(stats)

        table_card = Card(); tl = QtWidgets.QVBoxLayout(table_card); tl.setContentsMargins(14, 12, 14, 12); tl.setSpacing(10)
        top = QtWidgets.QHBoxLayout(); top.setSpacing(10)
        self.installed_title = QtWidgets.QLabel("Installed Programs (0)"); self.installed_title.setObjectName("sectionHeader")
        top.addWidget(self.installed_title); top.addStretch()
        self.app_search = QtWidgets.QLineEdit(); self.app_search.setPlaceholderText("⌕  Search programs..."); self.app_search.setMinimumWidth(230)
        self.app_search.textChanged.connect(self._reset_app_page_and_populate); top.addWidget(self.app_search)
        self.app_filter = QtWidgets.QComboBox(); self.app_filter.addItems(["All Programs", "Large Programs", "Recently Installed", "Older Programs", "Unknown Size"])
        self.app_filter.currentTextChanged.connect(self._reset_app_page_and_populate); top.addWidget(self.app_filter)
        self.app_sort = QtWidgets.QComboBox(); self.app_sort.addItems(["Sort: Name", "Sort: Size (Largest)", "Sort: Publisher", "Sort: Install Date"])
        self.app_sort.currentTextChanged.connect(self._reset_app_page_and_populate); top.addWidget(self.app_sort)
        refresh_btn = QtWidgets.QPushButton("⟳  Refresh"); refresh_btn.setObjectName("primaryAction"); refresh_btn.clicked.connect(self.load_installed_apps); top.addWidget(refresh_btn)
        tl.addLayout(top)

        self.apps_table = QtWidgets.QTableWidget(0, 7); self.apps_table.setAlternatingRowColors(False); self.apps_table.setShowGrid(False)
        self.apps_table.setHorizontalHeaderLabels(["", "Program Name", "Publisher", "Install Date", "Size", "Category", "Action"])
        self.apps_table.verticalHeader().setVisible(False); self.apps_table.verticalHeader().setDefaultSectionSize(42)
        hh=self.apps_table.horizontalHeader(); hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed); self.apps_table.setColumnWidth(0, 34)
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch); hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents); hh.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents); hh.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.Fixed); self.apps_table.setColumnWidth(6, 142)
        self.apps_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows); tl.addWidget(self.apps_table, 1)

        bottom=QtWidgets.QHBoxLayout(); self.app_status_label=QtWidgets.QLabel("Scanning installed software..."); self.app_status_label.setStyleSheet(f"color:{MUTED};")
        bottom.addWidget(self.app_status_label); bottom.addStretch()
        self.app_prev=QtWidgets.QPushButton("‹"); self.app_prev.clicked.connect(lambda: self._change_app_page(-1)); bottom.addWidget(self.app_prev)
        self.app_page_label=QtWidgets.QLabel("Page 1 / 1"); self.app_page_label.setStyleSheet("font-weight:700;color:#334155;padding:0 8px;"); bottom.addWidget(self.app_page_label)
        self.app_next=QtWidgets.QPushButton("›"); self.app_next.clicked.connect(lambda: self._change_app_page(1)); bottom.addWidget(self.app_next)
        self.uninstall_selected_btn=QtWidgets.QPushButton("Uninstall Selected (0)"); self.uninstall_selected_btn.setObjectName("primaryAction"); self.uninstall_selected_btn.setEnabled(False)
        self.uninstall_selected_btn.clicked.connect(self.action_uninstall_selected); bottom.addWidget(self.uninstall_selected_btn)
        tl.addLayout(bottom); outer.addWidget(table_card, 1)

        self.installed_apps=[]; self.app_page=0; self.app_page_size=10; self.current_uninstaller_tab="Installed Programs"
        QtCore.QTimer.singleShot(250, self.load_installed_apps)
        return page

    def smart_stat_card(self, icon, title, value, sub, color, value_attr):
        card=Card(); l=QtWidgets.QHBoxLayout(card); l.setContentsMargins(14, 12, 14, 12); l.setSpacing(10)
        badge=QtWidgets.QLabel(icon); badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); badge.setFixedSize(42,42)
        badge.setStyleSheet(f"background:{color}18;color:{color};border-radius:21px;font-size:19px;font-weight:900;"); l.addWidget(badge)
        text=QtWidgets.QVBoxLayout(); text.setSpacing(2); t=QtWidgets.QLabel(title); t.setObjectName("cardTitle"); v=QtWidgets.QLabel(value); v.setObjectName("cardValue"); v.setStyleSheet("font-size:21px;font-weight:800;color:#0f172a;")
        setattr(self,value_attr,v); d=QtWidgets.QLabel(sub); d.setStyleSheet(f"color:{MUTED};font-size:9px;"); d.setWordWrap(True); text.addWidget(t); text.addWidget(v); text.addWidget(d); l.addLayout(text,1); return card

    def small_stat_card(self, title, value, sub, color):
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        t = QtWidgets.QLabel(title)
        t.setObjectName("cardTitle")
        v = QtWidgets.QLabel(value)
        v.setObjectName("cardValue")
        s = QtWidgets.QLabel(sub)
        s.setStyleSheet(f"color:{MUTED};")
        l.addWidget(t)
        l.addWidget(v)
        l.addWidget(s)
        return card

    def create_ai_page(self):
        page, outer = self.page_shell("RUL Prediction", "Condition-based remaining useful life estimation")
        row = QtWidgets.QHBoxLayout()
        self.ai_score_value = QtWidgets.QLabel("0 / 100")
        score_card = Card()
        sc = QtWidgets.QVBoxLayout(score_card)
        sc.addWidget(QtWidgets.QLabel("Overall Health Score"))
        self.ai_score_value.setObjectName("cardValue")
        sc.addWidget(self.ai_score_value)
        row.addWidget(score_card)
        # Same card design; only Prediction Mode is replaced.
        self.ai_lifespan_card = self.small_stat_card(
            "Predicted Lifespan", "Calculating...", "Live RUL estimate", ORANGE
        )
        self.ai_lifespan_value = self.ai_lifespan_card.findChild(QtWidgets.QLabel, "cardValue")
        row.addWidget(self.ai_lifespan_card)
        self.ai_risk_card = self.small_stat_card("Risk Level", "Low", "Updated every interval", RED)
        self.ai_risk_value = self.ai_risk_card.findChild(QtWidgets.QLabel, "cardValue")
        row.addWidget(self.ai_risk_card)
        self.ai_data_card = self.small_stat_card("AI Model Status", "Checking...", "NASA model is optional", GREEN)
        self.ai_data_value = self.ai_data_card.findChild(QtWidgets.QLabel, "cardValue")
        row.addWidget(self.ai_data_card)
        outer.addLayout(row)

        body = QtWidgets.QHBoxLayout()
        chart = Card()
        cl = QtWidgets.QVBoxLayout(chart)
        cl.addWidget(QtWidgets.QLabel("Health Score Trend"))
        self.ai_graph = pg.PlotWidget()
        self.ai_graph.setBackground("white")
        self.ai_graph.showGrid(x=True, y=True, alpha=0.18)
        self.ai_graph.setYRange(0, 100)
        self.ai_graph.setLabel("left", "Health Score")
        self.ai_graph.setLabel("bottom", "Monitoring samples")
        self.ai_graph.addLegend(offset=(-12, 10), labelTextColor="#334155", brush=pg.mkBrush(255, 255, 255, 225), pen=pg.mkPen("#e2e8f0"))
        cl.addWidget(self.ai_graph)
        body.addWidget(chart, 2)

        risks = Card()
        rl = QtWidgets.QVBoxLayout(risks)
        rl.addWidget(QtWidgets.QLabel("Component Risk"))
        self.risk_bars = {}
        for name in ["CPU", "Temperature", "Storage", "RAM", "Battery"]:
            rowb = QtWidgets.QHBoxLayout()
            rowb.addWidget(QtWidgets.QLabel(name))
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            rowb.addWidget(bar)
            lab = QtWidgets.QLabel("--")
            rowb.addWidget(lab)
            rl.addLayout(rowb)
            self.risk_bars[name] = (bar, lab)
        body.addWidget(risks, 1)
        outer.addLayout(body, 1)

        self.ai_insights_list = QtWidgets.QListWidget()
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        l.addWidget(QtWidgets.QLabel("Live Insights"))
        l.addWidget(self.ai_insights_list)
        outer.addWidget(card)
        return page

    def create_health_history_page(self):
        page, outer = self.page_shell("Health History", "Historical health score and component trends")

        top = Card()
        tl = QtWidgets.QVBoxLayout(top)
        title = QtWidgets.QLabel("Overall Health Score Trend")
        title.setObjectName("sectionHeader")
        tl.addWidget(title)
        self.history_health_graph = pg.PlotWidget()
        self.history_health_graph.setBackground("white")
        self.history_health_graph.showGrid(x=True, y=True)
        self.history_health_graph.setYRange(0, 100)
        self.history_health_graph.setLabel("left", "Health Score")
        self.history_health_graph.setLabel("bottom", "Monitoring Samples")
        self.history_health_graph.addLegend(offset=(-12, 10), labelTextColor="#334155", brush=pg.mkBrush(255, 255, 255, 225), pen=pg.mkPen("#e2e8f0"))
        tl.addWidget(self.history_health_graph)
        outer.addWidget(top, 1)

        bottom = Card()
        bl = QtWidgets.QVBoxLayout(bottom)
        subtitle = QtWidgets.QLabel("Component Health Trends")
        subtitle.setObjectName("sectionHeader")
        bl.addWidget(subtitle)
        self.history_component_graph = pg.PlotWidget()
        self.history_component_graph.setBackground("white")
        self.history_component_graph.showGrid(x=True, y=True)
        self.history_component_graph.setYRange(0, 100)
        self.history_component_graph.setLabel("left", "Condition / Usage")
        self.history_component_graph.setLabel("bottom", "Monitoring Samples")
        self.history_component_graph.addLegend(offset=(-12, 10), labelTextColor="#334155", brush=pg.mkBrush(255, 255, 255, 225), pen=pg.mkPen("#e2e8f0"))
        bl.addWidget(self.history_component_graph)
        outer.addWidget(bottom, 1)
        return page

    def create_recommendations_page(self):
        page, outer = self.page_shell("Recommendations", "AI-powered maintenance recommendations")
        filters = QtWidgets.QHBoxLayout()
        for f in ["All Recommendations", "Performance", "Security", "Storage", "Battery", "System"]:
            btn = QtWidgets.QPushButton(f)
            btn.clicked.connect(lambda checked=False, name=f: self.action_filter_recommendations(name))
            filters.addWidget(btn)
        filters.addStretch()
        outer.addLayout(filters)

        row = QtWidgets.QHBoxLayout()
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        self.recs_header = QtWidgets.QLabel("Recommendations")
        self.recs_header.setObjectName("sectionHeader")
        l.addWidget(self.recs_header)
        self.recs_table = QtWidgets.QTableWidget(0, 5)
        self.recs_table.setAlternatingRowColors(True)
        self.recs_table.setShowGrid(False)
        self.recs_table.setHorizontalHeaderLabels(["Recommendation", "Category", "Priority", "Reason", "Action"])
        self.recs_table.horizontalHeader().setStretchLastSection(True)
        self.recs_table.verticalHeader().setDefaultSectionSize(52)
        l.addWidget(self.recs_table)
        row.addWidget(card, 2)

        side = Card()
        sl = QtWidgets.QVBoxLayout(side)
        sl.addWidget(QtWidgets.QLabel("Action Status"))
        self.recommendation_status = QtWidgets.QLabel("Every action button is connected to a real system-safe workflow.")
        self.recommendation_status.setWordWrap(True)
        self.recommendation_status.setStyleSheet("background:#ecfdf5;padding:18px;border-radius:12px;")
        sl.addWidget(self.recommendation_status)
        sl.addWidget(QtWidgets.QLabel("Action Log"))
        self.action_log_list = QtWidgets.QListWidget()
        sl.addWidget(self.action_log_list)
        row.addWidget(side, 1)
        outer.addLayout(row, 1)

        self.populate_recommendations()
        return page

    def create_system_data_page(self):
        page, outer = self.page_shell("Complete System Data", "Read-only live telemetry and hardware inventory used by the prediction engine")
        toolbar = QtWidgets.QHBoxLayout()
        self.system_data_summary = QtWidgets.QLabel("Collecting complete system information...")
        self.system_data_summary.setStyleSheet("color:#475569;font-weight:600;")
        toolbar.addWidget(self.system_data_summary)
        toolbar.addStretch()
        refresh = QtWidgets.QPushButton("Refresh Inventory")
        refresh.setObjectName("primaryAction")
        refresh.clicked.connect(self.action_refresh_inventory)
        toolbar.addWidget(refresh)
        export = QtWidgets.QPushButton("Export JSON")
        export.clicked.connect(self.action_export_system_json)
        toolbar.addWidget(export)
        outer.addLayout(toolbar)

        card = Card(); layout = QtWidgets.QVBoxLayout(card)
        self.system_data_table = QtWidgets.QTableWidget(0, 3)
        self.system_data_table.setHorizontalHeaderLabels(["Category", "Metric", "Current Value"])
        self.system_data_table.setAlternatingRowColors(True)
        self.system_data_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.system_data_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.system_data_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.system_data_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.system_data_table)
        outer.addWidget(card, 1)
        note = QtWidgets.QLabel("Privacy: this page reads local operating-system telemetry only. Unsupported sensor values are shown as unavailable; no fake values are inserted.")
        note.setWordWrap(True); note.setStyleSheet("color:#64748b;background:#eff6ff;padding:10px;border-radius:8px;")
        outer.addWidget(note)
        return page

    def create_reports_page(self):
        page, outer = self.page_shell("Reports", "Generate real-time system reports")
        row = QtWidgets.QHBoxLayout()
        self.report_combo = QtWidgets.QComboBox()
        self.report_combo.addItems(["Complete System Report", "Performance Report", "Security Report"])
        row.addWidget(self.report_combo)
        generate = QtWidgets.QPushButton("Generate TXT")
        generate.setObjectName("primaryAction")
        generate.clicked.connect(self.action_generate_report)
        row.addWidget(generate)
        for text, fmt in [("Export PDF", "pdf"), ("Export CSV", "csv"), ("Export HTML", "html")]:
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda checked=False, f=fmt: self.action_export_report(f))
            row.addWidget(b)
        outer.addLayout(row)

        self.reports_table = QtWidgets.QTableWidget(0, 3)
        self.reports_table.setAlternatingRowColors(True)
        self.reports_table.setShowGrid(False)
        self.reports_table.setHorizontalHeaderLabels(["Type", "Created", "File"])
        self.reports_table.horizontalHeader().setStretchLastSection(True)
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        l.addWidget(self.reports_table)
        outer.addWidget(card, 1)
        return page

    def create_settings_page(self):
        page, outer = self.page_shell("Settings", "Configure application preferences")
        columns = QtWidgets.QHBoxLayout(); columns.setSpacing(10)

        left = Card(); ll = QtWidgets.QVBoxLayout(left); ll.setContentsMargins(14, 12, 14, 12); ll.setSpacing(9)
        h = QtWidgets.QLabel("General Settings"); h.setObjectName("sectionHeader"); ll.addWidget(h)
        for text, checked in [("Start with Windows", False), ("Minimize to System Tray", True), ("Check for Updates on Startup", True)]:
            cb = QtWidgets.QCheckBox(text); cb.setChecked(checked); ll.addWidget(cb)
        ll.addSpacing(8)
        h2 = QtWidgets.QLabel("Monitoring Settings"); h2.setObjectName("sectionHeader"); ll.addWidget(h2)
        form = QtWidgets.QFormLayout(); form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.interval = QtWidgets.QSpinBox(); self.interval.setRange(1,60); self.interval.setValue(3); self.interval.setSuffix(" seconds")
        self.history_days = QtWidgets.QSpinBox(); self.history_days.setRange(1,365); self.history_days.setValue(30); self.history_days.setSuffix(" days")
        form.addRow("Monitoring Interval", self.interval); form.addRow("History Retention", self.history_days)
        ll.addLayout(form); ll.addStretch(); columns.addWidget(left,1)

        right = Card(); rl = QtWidgets.QVBoxLayout(right); rl.setContentsMargins(14,12,14,12); rl.setSpacing(9)
        rh = QtWidgets.QLabel("Alerts"); rh.setObjectName("sectionHeader"); rl.addWidget(rh)
        self.warning_temp = QtWidgets.QSpinBox(); self.warning_temp.setRange(45,110); self.warning_temp.setValue(80); self.warning_temp.hide()
        self.critical_temp = QtWidgets.QSpinBox(); self.critical_temp.setRange(60,120); self.critical_temp.setValue(90); self.critical_temp.hide()
        for text in ["High CPU Usage (> 80%)", "High Temperature (> 70 °C)", "Low Battery (< 20%)", "Low Disk Space (< 10%)"]:
            cb=QtWidgets.QCheckBox(text); cb.setChecked(True); rl.addWidget(cb)
        rl.addSpacing(8)
        th=QtWidgets.QLabel("Theme"); th.setObjectName("sectionHeader"); rl.addWidget(th)
        theme=QtWidgets.QComboBox(); theme.addItems(["Light", "System Default"]); rl.addWidget(theme); rl.addStretch(); columns.addWidget(right,1)
        outer.addLayout(columns,1)
        actions=QtWidgets.QHBoxLayout(); actions.addStretch()
        save=QtWidgets.QPushButton("Save Settings"); save.setObjectName("primaryAction"); save.clicked.connect(self.action_save_settings)
        reset=QtWidgets.QPushButton("Reset to Default"); reset.clicked.connect(lambda: (self.interval.setValue(3), self.history_days.setValue(30)))
        actions.addWidget(save); actions.addWidget(reset); actions.addStretch(); outer.addLayout(actions)
        return page

    def create_about_page(self):
        page, outer = self.page_shell("About", "Application and real-time system information")
        self.about_label = QtWidgets.QLabel(self.get_system_info_text())
        self.about_label.setWordWrap(True)
        card = Card()
        l = QtWidgets.QVBoxLayout(card)
        l.addWidget(self.about_label)
        outer.addWidget(card)
        outer.addStretch()
        return page

    # ----------------------- Real-time data -----------------------

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)

    def get_warning_temp(self) -> int:
        widget = getattr(self, "warning_temp", None)
        if widget is not None:
            try:
                return int(widget.value())
            except Exception:
                pass
        return int(getattr(self, "temp_warning_value", 80))

    def get_critical_temp(self) -> int:
        widget = getattr(self, "critical_temp", None)
        if widget is not None:
            try:
                return int(widget.value())
            except Exception:
                pass
        return int(getattr(self, "temp_critical_value", 90))

    def get_monitor_interval(self) -> int:
        widget = getattr(self, "interval", None)
        if widget is not None:
            try:
                return int(widget.value())
            except Exception:
                pass
        return int(getattr(self, "monitor_interval_value", 3))

    def get_metrics(self):
        # CPU/RAM are sampled first so the thermal fallback uses current system load.
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        temp = self.get_temperature(cpu, ram)
        hw = self._collect_rul_hardware_metrics()
        battery = psutil.sensors_battery()
        battery_percent = battery.percent if battery else None
        battery_health = hw.get("battery_health") if hw.get("battery_health") is not None else battery_percent
        display_battery = battery_health if battery_health is not None else 100.0
        live = self.probe.fast_snapshot(temp, display_battery)
        live["battery_present"] = battery is not None
        live["cpu_usage"] = round(cpu, 1)
        live["ram_usage"] = round(ram, 1)
        # Multi-signal condition score. Missing optional values are excluded.
        penalties = []
        def penalty(value, weight):
            if value is not None:
                penalties.append((max(0.0, min(100.0, float(value))), weight))
        penalty(live.get("cpu_usage"), .18)
        penalty(live.get("ram_usage"), .15)
        penalty(max(0.0, live.get("temperature", 0)-40)*1.8, .20)
        penalty(live.get("disk_usage"), .12)
        penalty(live.get("swap_usage"), .07)
        penalty(min(100, live.get("process_count", 0)/3), .04)
        if battery_health is not None: penalty(100-float(battery_health), .14)
        if hw.get("ssd_smart_health") is not None: penalty(100-float(hw["ssd_smart_health"]), .10)
        health = 100 - (sum(v*w for v,w in penalties)/sum(w for _,w in penalties) if penalties else 0)
        live["health_score"] = round(max(0, min(100, health)), 1)
        return live

    def get_temperature(self, cpu_usage=None, ram_usage=None):
        """Return a real sensor temperature when available; otherwise estimate it from live load.

        The fallback is deterministic (never random/static): CPU and RAM utilisation are
        converted to thermal load, recent load is averaged to reduce spikes, and exponential
        smoothing gives the estimate realistic thermal inertia.
        """
        try:
            temps = psutil.sensors_temperatures()
            values = [float(entry.current) for arr in temps.values() for entry in arr
                      if entry.current is not None and 10.0 <= float(entry.current) <= 120.0]
            if values:
                self._temperature_source = "sensor"
                self._estimated_temperature = float(max(values))
                return self._estimated_temperature
        except Exception:
            pass

        cpu = safe_float(cpu_usage if cpu_usage is not None else psutil.cpu_percent(interval=None))
        ram = safe_float(ram_usage if ram_usage is not None else psutil.virtual_memory().percent)

        load_history = getattr(self, "_thermal_load_history", [])
        load_history.append((cpu, ram))
        self._thermal_load_history = load_history[-20:]
        cpu_avg = sum(c for c, _ in self._thermal_load_history) / len(self._thermal_load_history)
        ram_avg = sum(r for _, r in self._thermal_load_history) / len(self._thermal_load_history)

        # Deterministic load-to-temperature estimate. CPU dominates heat generation;
        # RAM contributes a smaller sustained-load term. The nonlinear CPU term makes
        # high utilisation progressively hotter without inventing random readings.
        target = 32.0 + (0.34 * cpu_avg) + (0.07 * ram_avg) + (0.0012 * cpu_avg * cpu_avg)
        target = max(30.0, min(95.0, target))

        previous = getattr(self, "_estimated_temperature", None)
        if previous is None:
            estimated = target
        else:
            interval = max(1.0, float(self.get_monitor_interval()))
            alpha = 1.0 - pow(0.5, interval / 25.0)
            estimated = previous + alpha * (target - previous)

        self._temperature_source = "estimated_cpu_ram"
        self._estimated_temperature = max(30.0, min(95.0, estimated))
        return self._estimated_temperature

    def refresh_all(self):
        self.current_metrics = self.get_metrics()
        self.metrics_history.append(self.current_metrics)
        self.metrics_history = self.metrics_history[-60:]
        self.update_dashboard()
        self.update_graphs()
        self.update_storage_drives()
        self.update_ai()
        self.populate_recommendations()
        self.about_label.setText(self.get_system_info_text())
        self.update_system_data_table()

        now = datetime.now().strftime("%I:%M:%S %p")
        for label in self.last_updated_labels:
            label.setText(f"Last Updated: {now}")

    def update_dashboard(self):
        for key, (val, status, suffix, exp) in self.metric_widgets.items():
            v = self.current_metrics.get(key, 0)
            val.setText(f"{int(v)}/100" if key == "health_score" else f"{int(v)}{suffix}")
            status_text, color = self.status_for_metric(key, v)
            status.setText(status_text)
            status.setStyleSheet(f"font-size:18px;font-weight:800;color:{color};")

        score = self.current_metrics.get("health_score", 0)
        uptime_seconds = int(self.current_metrics.get("uptime_seconds", 0))
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        if hasattr(self, "dashboard_uptime_value"):
            self.dashboard_uptime_value.setText(f"{days}d {hours}h {minutes}m")
        if hasattr(self, "dashboard_rul_value"):
            self.dashboard_rul_value.setText(self._format_rul(self._estimate_remaining_useful_life()))
        if hasattr(self, "health_ring"):
            self.health_ring.setValue(score)
        self.thermal_temp.setText(f"{int(self.current_metrics.get('temperature', 0))}°C")
        self.thermal_ring.setValue(self.current_metrics.get("temperature", 0))

        temp = self.current_metrics.get("temperature", 0)
        if temp >= self.get_critical_temp():
            self.thermal_status.setText("Critical")
            self.thermal_status.setStyleSheet(f"font-size:30px;font-weight:900;color:{RED};")
            self.thermal_message.setText("Critical heat level. Reduce system load immediately.")
        elif temp >= self.get_warning_temp():
            self.thermal_status.setText("Warning")
            self.thermal_status.setStyleSheet(f"font-size:30px;font-weight:900;color:{ORANGE};")
            self.thermal_message.setText("Temperature is high. Ensure ventilation and close heavy apps.")
        else:
            self.thermal_status.setText("Normal")
            self.thermal_status.setStyleSheet(f"font-size:30px;font-weight:900;color:{GREEN};")
            self.thermal_message.setText("Temperature is within safe range.")

        if score >= 75:
            self.side_health_value.setText("Good")
            self.side_health_value.setStyleSheet(f"font-size:22px;font-weight:900;color:{GREEN};")
        elif score >= 50:
            self.side_health_value.setText("Medium")
            self.side_health_value.setStyleSheet(f"font-size:22px;font-weight:900;color:{ORANGE};")
        else:
            self.side_health_value.setText("Critical")
            self.side_health_value.setStyleSheet(f"font-size:22px;font-weight:900;color:{RED};")
        if hasattr(self, "footer_status"):
            label = "All systems operational" if score >= 75 else ("Attention recommended" if score >= 50 else "Immediate attention required")
            color = GREEN if score >= 75 else (ORANGE if score >= 50 else RED)
            self.footer_status.setText("●  System Status: " + label)
            self.footer_status.setStyleSheet(f"color:{color};font-size:9px;font-weight:700;")

        # Detailed monitoring cards
        if hasattr(self, "monitor_metric_values"):
            swap = psutil.swap_memory().percent
            freq = psutil.cpu_freq()
            values = {
                **self.current_metrics,
                "swap": self.current_metrics.get("swap_usage", swap),
                "cpu_frequency": self.current_metrics.get("cpu_frequency_ghz", (freq.current / 1000.0) if freq else 0.0),
                "uptime": f"{days}d {hours}h {minutes}m",
            }
            for key, (label, suffix) in self.monitor_metric_values.items():
                value = values.get(key, 0)
                if key == "uptime":
                    label.setText(str(value))
                elif key == "cpu_frequency":
                    label.setText(f"{value:.2f}{suffix}")
                else:
                    label.setText(f"{int(value)}{suffix}")

        # Compact risk summary on the dashboard
        if hasattr(self, "dashboard_risk_labels"):
            risk_values = {
                "Battery": max(0, 100 - self.current_metrics.get("battery_health", 100)),
                "Temperature": min(100, max(0, (temp - 40) * 2.0)),
                "CPU": self.current_metrics.get("cpu_usage", 0),
                "RAM": self.current_metrics.get("ram_usage", 0),
                "Storage": self.current_metrics.get("disk_usage", 0),
            }
            for name, risk in risk_values.items():
                if risk >= 75:
                    text, color = "High Risk", RED
                elif risk >= 50:
                    text, color = "Medium Risk", ORANGE
                else:
                    text, color = "Low Risk", GREEN
                label = self.dashboard_risk_labels[name]
                label.setText(text)
                label.setStyleSheet(f"font-weight:800;color:{color};")

    def status_for_metric(self, key, value):
        if key == "temperature":
            if value >= self.get_critical_temp():
                return "Critical", RED
            if value >= self.get_warning_temp():
                return "Warning", ORANGE
            return "Good", GREEN
        if key in {"cpu_usage", "ram_usage", "disk_usage"}:
            if value >= 90:
                return "Critical", RED
            if value >= 75:
                return "High", ORANGE
            return "Good", GREEN
        if key == "battery_health":
            if value < 20:
                return "Low", RED
            if value < 40:
                return "Medium", ORANGE
            return "Good", GREEN
        if key == "health_score":
            if value < 50:
                return "Critical", RED
            if value < 75:
                return "Medium", ORANGE
            return "Good", GREEN
        return "Good", GREEN

    def update_graphs(self):
        xs = list(range(len(self.metrics_history)))
        cpu = [m["cpu_usage"] for m in self.metrics_history]
        ram = [m["ram_usage"] for m in self.metrics_history]
        temp = [m["temperature"] for m in self.metrics_history]

        for graph in [self.dashboard_graph, self.monitoring_graph]:
            graph.clear()
            graph.plot(xs, cpu, pen=pg.mkPen(BLUE, width=2), name="CPU Usage (%)")
            graph.plot(xs, ram, pen=pg.mkPen(GREEN, width=2), name="RAM Usage (%)")
            graph.plot(xs, temp, pen=pg.mkPen(ORANGE, width=2), name="Temperature (°C)")

        self.thermal_graph.clear()
        self.thermal_graph.plot(xs, temp, pen=pg.mkPen(RED, width=2), name="Temperature (°C)")

        self.ai_graph.clear()
        scores = [m["health_score"] for m in self.metrics_history]
        self.ai_graph.plot(xs, scores, pen=pg.mkPen(BLUE, width=2), name="Overall Health Score")

        if hasattr(self, "history_health_graph"):
            self.history_health_graph.clear()
            self.history_health_graph.plot(xs, scores, pen=pg.mkPen(GREEN, width=3), name="Overall Health Score")
        if hasattr(self, "history_component_graph"):
            self.history_component_graph.clear()
            self.history_component_graph.plot(xs, [m["battery_health"] for m in self.metrics_history], pen=pg.mkPen(GREEN, width=2), name="Battery Health (%)")
            self.history_component_graph.plot(xs, cpu, pen=pg.mkPen(BLUE, width=2), name="CPU Usage (%)")
            self.history_component_graph.plot(xs, temp, pen=pg.mkPen(RED, width=2), name="Temperature (°C)")
            self.history_component_graph.plot(xs, ram, pen=pg.mkPen(PURPLE, width=2), name="RAM Usage (%)")
            self.history_component_graph.plot(xs, [m["disk_usage"] for m in self.metrics_history], pen=pg.mkPen(ORANGE, width=2), name="Storage Usage (%)")

    def update_storage_drives(self):
        while self.drive_cards.count():
            item = self.drive_cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        drives = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                drives.append((part.device or part.mountpoint, int(usage.percent), f"{usage.total // (1024 ** 3)} GB", f"{usage.free // (1024 ** 3)} GB"))
            except Exception:
                pass

        for i, d in enumerate(drives[:3]):
            self.drive_cards.addWidget(self.drive_card(*d, [BLUE, GREEN, PURPLE][i % 3]))

        if drives:
            used = drives[0][1]
            self.storage_progress.setValue(used)
            self.storage_progress.setFormat(f"{used}% used")
            self.storage_breakdown_text.setText(f"System drive: {drives[0][0]}\nTotal: {drives[0][2]}\nFree: {drives[0][3]}")
            self.storage_health_label.setText("Good" if used < 80 else "Warning")
            self.storage_health_label.setStyleSheet(f"font-size:24px;font-weight:900;color:{GREEN if used < 80 else ORANGE};")

    def _collect_rul_hardware_metrics(self):
        """Collect optional battery wear/cycle and SSD health without inventing values."""
        now = time.monotonic()
        if self._rul_hardware_cache and now - self._rul_hardware_cache_at < 300:
            return self._rul_hardware_cache
        result = {"battery_health": None, "battery_wear": None,
                  "battery_cycles": None, "ssd_smart_health": None}

        if platform.system() == "Linux":
            for bat in Path("/sys/class/power_supply").glob("BAT*"):
                try:
                    def read_num(name):
                        path = bat / name
                        return float(path.read_text().strip()) if path.exists() else None
                    full = read_num("energy_full") or read_num("charge_full")
                    design = read_num("energy_full_design") or read_num("charge_full_design")
                    cycles = read_num("cycle_count")
                    if full is not None and design and design > 0:
                        health = max(0.0, min(100.0, full / design * 100.0))
                        result["battery_health"] = health
                        result["battery_wear"] = 100.0 - health
                    if cycles is not None and cycles >= 0:
                        result["battery_cycles"] = cycles
                    break
                except Exception:
                    continue
        elif platform.system() == "Windows":
            ps = r'''$s = Get-CimInstance -Namespace root/wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue | Select-Object -First 1
$f = Get-CimInstance -Namespace root/wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue | Select-Object -First 1
$c = Get-CimInstance -Namespace root/wmi -ClassName BatteryCycleCount -ErrorAction SilentlyContinue | Select-Object -First 1
[PSCustomObject]@{Design=$s.DesignedCapacity; Full=$f.FullChargedCapacity; Cycles=$c.CycleCount} | ConvertTo-Json -Compress'''
            try:
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", ps], text=True,
                    stderr=subprocess.DEVNULL, timeout=8, encoding="utf-8", errors="ignore").strip()
                data = json.loads(out) if out else {}
                design, full = safe_float(data.get("Design")), safe_float(data.get("Full"))
                cycles = data.get("Cycles")
                if design > 0 and full > 0:
                    health = max(0.0, min(100.0, full / design * 100.0))
                    result["battery_health"] = health
                    result["battery_wear"] = 100.0 - health
                if cycles is not None and safe_float(cycles, -1) >= 0:
                    result["battery_cycles"] = safe_float(cycles)
            except Exception:
                pass

        try:
            smartctl = shutil.which("smartctl")
            if smartctl:
                scan = subprocess.check_output([smartctl, "--scan-open"], text=True,
                    stderr=subprocess.DEVNULL, timeout=8, errors="ignore")
                values = []
                for line in scan.splitlines():
                    device = line.split()[0] if line.strip() else ""
                    if not device:
                        continue
                    raw = subprocess.check_output([smartctl, "-a", "-j", device], text=True,
                        stderr=subprocess.DEVNULL, timeout=8, errors="ignore")
                    data = json.loads(raw)
                    pct = data.get("percentage_used")
                    if pct is None:
                        pct = data.get("nvme_smart_health_information_log", {}).get("percentage_used")
                    if pct is not None:
                        values.append(max(0.0, min(100.0, 100.0 - safe_float(pct))))
                if values:
                    result["ssd_smart_health"] = min(values)
        except Exception:
            pass
        self._rul_hardware_cache, self._rul_hardware_cache_at = result, now
        return result

    @staticmethod
    def _rul_factor(value, good, bad, higher_is_better=False):
        if value is None:
            return None
        value = safe_float(value)
        if higher_is_better:
            if value >= good: return 1.0
            if value <= bad: return 0.0
            return (value - bad) / (good - bad)
        if value <= good: return 1.0
        if value >= bad: return 0.0
        return (bad - value) / (bad - good)

    def _estimate_remaining_useful_life(self):
        """Weighted RUL estimate from available live metrics and historical trend."""
        hw = self._collect_rul_hardware_metrics()
        recent = self.metrics_history[-20:] or [self.current_metrics]
        cpu_avg = sum(safe_float(m.get("cpu_usage")) for m in recent) / len(recent)
        temp_avg = sum(safe_float(m.get("temperature")) for m in recent) / len(recent)
        ram = safe_float(self.current_metrics.get("ram_usage"))
        disk = safe_float(self.current_metrics.get("disk_usage"))
        uptime_days = max(0.0, (time.time() - psutil.boot_time()) / 86400.0)
        scores = []
        def add(value, weight):
            if value is not None: scores.append((max(0.0, min(1.0, value)), weight))
        add(self._rul_factor(hw.get("battery_health"), 90, 55, True), .20)
        add(self._rul_factor(hw.get("battery_wear"), 10, 45), .10)
        add(self._rul_factor(hw.get("battery_cycles"), 150, 1000), .08)
        add(self._rul_factor(cpu_avg, 35, 90), .10)
        add(self._rul_factor(temp_avg, 55, 95), .16)
        add(self._rul_factor(ram, 55, 95), .08)
        add(self._rul_factor(disk, 65, 95), .08)
        add(self._rul_factor(hw.get("ssd_smart_health"), 90, 40, True), .12)
        add(self._rul_factor(uptime_days, 2, 30), .03)
        health_values = [safe_float(m.get("health_score")) for m in self.metrics_history if m.get("health_score") is not None]
        current_health = health_values[-1] if health_values else safe_float(self.current_metrics.get("health_score"), 50)
        add(self._rul_factor(current_health, 90, 40, True), .05)
        if not scores: return None
        condition = sum(v*w for v,w in scores) / sum(w for _,w in scores)
        raw_years = 0.5 + 4.5 * (condition ** 1.35)
        if len(health_values) >= 10:
            split = len(health_values) // 2
            old_avg = sum(health_values[:split]) / split
            new_avg = sum(health_values[split:]) / (len(health_values)-split)
            trend = max(-10.0, min(10.0, new_avg-old_avg))
            raw_years *= 1.0 + trend * .006
        now = time.monotonic()
        elapsed = max(.1, now-self._rul_last_update)
        self._rul_last_update = now
        alpha = 1.0 - pow(.5, elapsed/120.0)
        if self._rul_smoothed_years is None: self._rul_smoothed_years = raw_years
        else: self._rul_smoothed_years += alpha * (raw_years-self._rul_smoothed_years)
        return max(0.0, self._rul_smoothed_years)

    @staticmethod
    def _format_rul(years):
        if years is None: return "Unavailable"
        if years < 1.0:
            months = max(1, round(years*12))
            return f"{months} Month{'s' if months != 1 else ''} Remaining"
        return f"{years:.1f} Years Remaining"

    def update_ai(self):
        score = self.current_metrics.get("health_score", 0)
        self.ai_score_value.setText(f"{int(score)} / 100")
        lifespan = self._estimate_remaining_useful_life()
        if self.ai_lifespan_value is not None:
            self.ai_lifespan_value.setText(self._format_rul(lifespan))
        available = sum(1 for v in self.current_metrics.values() if v is not None and not isinstance(v, (list, dict)))
        if hasattr(self, "ai_data_value"):
            if self.research_predictor.ready:
                model_name = self.research_predictor.rul_bundle.get("model_name", "Trained")
                self.ai_data_value.setText(f"{model_name} Ready")
                self.ai_data_value.setToolTip(f"Research model trained; {available} live system metrics are currently available. Battery-cycle inference requires NASA-compatible cycle features.")
            else:
                self.ai_data_value.setText("Not Trained")
                self.ai_data_value.setToolTip("Add the NASA dataset to ai/dataset and run TRAIN_AI_MODEL.bat. The current lifespan remains condition-based.")
        if hasattr(self, "ai_risk_value"):
            risk_text = "Low" if score >= 75 else ("Medium" if score >= 50 else "High")
            self.ai_risk_value.setText(risk_text)
        risks = {
            "CPU": int(min(100, self.current_metrics.get("cpu_usage", 0))),
            "Temperature": int(min(100, max(0, self.current_metrics.get("temperature", 0)))),
            "Storage": int(min(100, self.current_metrics.get("disk_usage", 0))),
            "RAM": int(min(100, self.current_metrics.get("ram_usage", 0))),
            "Battery": int(min(100, max(0, 100 - self.current_metrics.get("battery_health", 100)))),
        }
        for name, (bar, lab) in self.risk_bars.items():
            value = risks.get(name, 0)
            bar.setValue(value)
            lab.setText(("High" if value >= 75 else "Medium" if value >= 45 else "Low") + f"\n{value}%")

        self.ai_insights_list.clear()
        if self.research_predictor.ready:
            self.ai_insights_list.addItem("NASA battery research model is trained and available. See ai/reports for measured evaluation results.")
        else:
            self.ai_insights_list.addItem("AI model is not trained yet. Add the NASA dataset and run TRAIN_AI_MODEL.bat; live condition monitoring remains active.")
        if self.current_metrics.get("cpu_usage", 0) > 75:
            self.ai_insights_list.addItem("CPU usage is high. Close heavy background apps.")
        if self.current_metrics.get("ram_usage", 0) > 75:
            self.ai_insights_list.addItem("RAM usage is high. Consider closing unused apps.")
        if self.current_metrics.get("disk_usage", 0) > 80:
            self.ai_insights_list.addItem("Disk usage is high. Scan junk and review large files.")
        if self.current_metrics.get("temperature", 0) > self.get_warning_temp():
            self.ai_insights_list.addItem("Temperature warning. Improve ventilation.")
        if all(self.current_metrics.get(key, 0) <= limit for key, limit in (("cpu_usage", 75), ("ram_usage", 75), ("disk_usage", 80), ("temperature", self.get_warning_temp()))):
            self.ai_insights_list.addItem("System is currently healthy.")

    def update_system_data_table(self):
        if not hasattr(self, "system_data_table"):
            return
        rows = self.probe.rows(self.current_metrics, self.system_inventory)
        self.system_data_table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.system_data_table.setItem(r, c, QtWidgets.QTableWidgetItem(value))
        self.system_data_summary.setText(f"{len(rows)} live and hardware fields available • Prediction uses all valid condition signals")

    def action_refresh_inventory(self):
        self.system_inventory = self.probe.static_snapshot(max_age=0)
        self.refresh_all()
        self.mark_action("Hardware inventory refreshed.")

    def action_export_system_json(self):
        payload = {"generated_at": datetime.now().isoformat(), "live": self.current_metrics, "hardware": self.system_inventory}
        path = self.reports_dir / f"complete_system_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self.mark_action(f"System data exported: {path.name}")
        self._show_message("Export Complete", f"Complete system data saved to:\n{path}")

    # ----------------------- Installed apps -----------------------

    def load_installed_apps(self):
        if hasattr(self, "app_status_label"):
            self.app_status_label.setText("Scanning Windows uninstall registry...")
        QtWidgets.QApplication.processEvents()
        self.installed_apps = self.read_installed_apps()
        self.app_page = 0
        self.populate_apps()
        self.mark_action(f"Detected {len(self.installed_apps)} installed programs.")

    @staticmethod
    def _parse_install_date(raw):
        raw=(raw or "").strip()
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
            try: return datetime.strptime(raw,fmt)
            except Exception: pass
        return None

    def read_installed_apps(self):
        if platform.system() != "Windows":
            return [{"name":"Installed program inventory requires Windows","publisher":platform.system(),"date":"","date_obj":None,"size":"","size_mb":0.0,"uninstall":"","quiet_uninstall":""}]
        ps = r'''$paths=@('HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'); foreach($p in $paths){Get-ItemProperty $p -ErrorAction SilentlyContinue | Where-Object {$_.DisplayName -and -not $_.SystemComponent} | Select-Object DisplayName,Publisher,InstallDate,EstimatedSize,UninstallString,QuietUninstallString,DisplayIcon | ConvertTo-Csv -NoTypeInformation}'''
        try:
            out=subprocess.check_output(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",ps],text=True,stderr=subprocess.STDOUT,timeout=35,encoding="utf-8-sig",errors="ignore")
            import io
            rows=list(csv.DictReader(io.StringIO(out))); apps=[]; seen=set()
            for row in rows:
                name=(row.get("DisplayName") or "").strip(); key=name.casefold()
                if not name or key in seen: continue
                seen.add(key); size_kb=safe_float(row.get("EstimatedSize"),0); size_mb=size_kb/1024 if size_kb else 0.0
                date_raw=(row.get("InstallDate") or "").strip(); date_obj=self._parse_install_date(date_raw)
                display_date=date_obj.strftime("%d-%m-%Y") if date_obj else (date_raw or "—")
                apps.append({"name":name,"publisher":(row.get("Publisher") or "Unknown").strip() or "Unknown","date":display_date,"date_obj":date_obj,"size":self._format_program_size(size_mb),"size_mb":size_mb,"uninstall":(row.get("UninstallString") or "").strip(),"quiet_uninstall":(row.get("QuietUninstallString") or "").strip(),"icon":(row.get("DisplayIcon") or "").strip()})
            return sorted(apps,key=lambda a:a["name"].casefold())[:1000]
        except Exception as exc:
            return [{"name":f"Unable to read installed programs: {exc}","publisher":"","date":"","date_obj":None,"size":"","size_mb":0.0,"uninstall":"","quiet_uninstall":""}]

    @staticmethod
    def _format_program_size(size_mb):
        if not size_mb: return "Unknown"
        return f"{size_mb/1024:.2f} GB" if size_mb>=1024 else f"{size_mb:.0f} MB"

    def _program_category(self, app):
        d=app.get("date_obj"); now=datetime.now()
        if d and (now-d).days<=90: return "Recently Installed","usageGreen"
        if d and (now-d).days>=365: return "Older Program","usageAmber"
        if not d: return "Date Unknown","usageRed"
        return "Installed","usageGreen"

    def _filtered_apps(self):
        query=self.app_search.text().strip().casefold() if hasattr(self,"app_search") else ""
        filt=self.app_filter.currentText() if hasattr(self,"app_filter") else "All Programs"
        rows=[a for a in self.installed_apps if query in (a.get("name","")+" "+a.get("publisher","")).casefold()]
        now=datetime.now()
        if filt=="Large Programs": rows=[a for a in rows if a.get("size_mb",0)>=500]
        elif filt=="Recently Installed": rows=[a for a in rows if a.get("date_obj") and (now-a["date_obj"]).days<=90]
        elif filt=="Older Programs": rows=[a for a in rows if a.get("date_obj") and (now-a["date_obj"]).days>=365]
        elif filt=="Unknown Size": rows=[a for a in rows if not a.get("size_mb")]
        sort=self.app_sort.currentText() if hasattr(self,"app_sort") else "Sort: Name"
        if sort=="Sort: Size (Largest)": rows.sort(key=lambda a:a.get("size_mb",0),reverse=True)
        elif sort=="Sort: Publisher": rows.sort(key=lambda a:a.get("publisher","").casefold())
        elif sort=="Sort: Install Date": rows.sort(key=lambda a:a.get("date_obj") or datetime.min,reverse=True)
        else: rows.sort(key=lambda a:a.get("name","").casefold())
        return rows

    def _reset_app_page_and_populate(self, *_): self.app_page=0; self.populate_apps()
    def _change_app_page(self, delta): self.app_page=max(0,self.app_page+delta); self.populate_apps()

    def populate_apps(self):
        if not hasattr(self,"apps_table"): return
        rows=self._filtered_apps(); total=len(rows); pages=max(1,(total+self.app_page_size-1)//self.app_page_size); self.app_page=min(self.app_page,pages-1)
        shown=rows[self.app_page*self.app_page_size:(self.app_page+1)*self.app_page_size]
        self.apps_table.setRowCount(len(shown)); self.installed_title.setText(f"Installed Programs ({total})")
        for r,app in enumerate(shown):
            check=QtWidgets.QCheckBox(); check.setProperty("app",app); check.stateChanged.connect(self._update_selected_count)
            wrap=QtWidgets.QWidget(); wl=QtWidgets.QHBoxLayout(wrap); wl.setContentsMargins(6,0,0,0); wl.addWidget(check); wl.addStretch(); self.apps_table.setCellWidget(r,0,wrap)
            for c,key in enumerate(("name","publisher","date","size"),start=1):
                item=QtWidgets.QTableWidgetItem(str(app.get(key,""))); item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable); self.apps_table.setItem(r,c,item)
            label_text,obj=self._program_category(app); badge=QtWidgets.QLabel(label_text); badge.setObjectName(obj); badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter); self.apps_table.setCellWidget(r,5,badge)
            action_wrap=QtWidgets.QWidget(); al=QtWidgets.QHBoxLayout(action_wrap); al.setContentsMargins(2,3,2,3); al.setSpacing(6)
            btn=QtWidgets.QPushButton("Uninstall"); btn.setObjectName("tableAction"); btn.clicked.connect(lambda checked=False,a=app:self.action_uninstall_app(a)); al.addWidget(btn)
            more=QtWidgets.QToolButton(); more.setObjectName("moreAction"); more.setText("⋮"); menu=QtWidgets.QMenu(more); info=menu.addAction("Program details"); info.triggered.connect(lambda checked=False,a=app:self.action_program_details(a)); settings=menu.addAction("Open Apps settings"); settings.triggered.connect(self.action_open_apps_settings); more.setMenu(menu); more.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup); al.addWidget(more); self.apps_table.setCellWidget(r,6,action_wrap)
        first=self.app_page*self.app_page_size+1 if total else 0; finish=min(total,(self.app_page+1)*self.app_page_size)
        self.app_status_label.setText(f"Showing {first} to {finish} of {total} programs"); self.app_page_label.setText(f"Page {self.app_page+1} / {pages}"); self.app_prev.setEnabled(self.app_page>0); self.app_next.setEnabled(self.app_page<pages-1)
        self._update_program_stats(); self._update_selected_count()

    def _update_program_stats(self):
        apps=self.installed_apps; now=datetime.now(); total_mb=sum(a.get("size_mb",0) for a in apps)
        self.program_total_value.setText(str(len(apps))); self.program_recent_value.setText(str(sum(1 for a in apps if a.get("date_obj") and (now-a["date_obj"]).days<=90)))
        self.program_old_value.setText(str(sum(1 for a in apps if a.get("date_obj") and (now-a["date_obj"]).days>=365))); self.program_large_value.setText(str(sum(1 for a in apps if a.get("size_mb",0)>=500)))
        self.program_space_value.setText(f"{total_mb/1024:.2f} GB" if total_mb else "Unknown")

    def _selected_apps(self):
        selected=[]
        for row in range(self.apps_table.rowCount()):
            w=self.apps_table.cellWidget(row,0); cb=w.findChild(QtWidgets.QCheckBox) if w else None
            if cb and cb.isChecked(): selected.append(cb.property("app"))
        return selected

    def _update_selected_count(self, *_):
        n=len(self._selected_apps()) if hasattr(self,"apps_table") else 0; self.uninstall_selected_btn.setText(f"Uninstall Selected ({n})"); self.uninstall_selected_btn.setEnabled(n>0)

    def action_uninstall_selected(self):
        apps=self._selected_apps()
        if not apps: return
        if len(apps)>1:
            reply=self._ask_question("Confirm Uninstall",f"Open the official uninstallers for {len(apps)} selected programs?\n\nEach program may show its own confirmation window.")
            if reply!=QtWidgets.QMessageBox.StandardButton.Yes: return
        for app in apps: self.action_uninstall_app(app, confirm=len(apps)==1)

    def action_program_details(self, app):
        self._show_message("Program Details",f"Name: {app.get('name','')}\nPublisher: {app.get('publisher','Unknown')}\nInstall date: {app.get('date','Unknown')}\nReported size: {app.get('size','Unknown')}\n\nWindows registry data may omit size or date for some programs.")

    def action_open_apps_settings(self):
        if platform.system()=="Windows": subprocess.Popen(["cmd","/c","start","","ms-settings:appsfeatures"],shell=False)

    # ----------------------- Recommendations -----------------------

    def recommendation_rows(self):
        rows = []
        m = self.current_metrics
        if m.get("cpu_usage", 0) > 70 or m.get("ram_usage", 0) > 70:
            rows.append(("Manage Startup Programs\nReduce boot/load impact.", "Performance", "Medium", "CPU/RAM usage is high", "Manage", self.action_manage_startup))
        if m.get("disk_usage", 0) > 70:
            rows.append(("Scan and Clean Temp Files\nFree safe temporary files.", "Storage", "High", "Disk usage is increasing", "Clean", self.action_scan_junk))
        if m.get("temperature", 0) > self.get_warning_temp():
            rows.append(("Thermal Check\nReduce temperature.", "System", "High", "Temperature warning detected", "Check Now", self.action_smart_scan))
        rows.append(("Generate Health Report\nSave latest metrics.", "System", "Low", "Keep maintenance history", "Generate", self.action_generate_report))
        if not rows:
            rows.append(("System Healthy\nNo immediate action required.", "System", "Low", "Current metrics look good", "Refresh", self.action_refresh))
        return rows

    def populate_recommendations(self):
        if not hasattr(self, "recs_table"):
            return
        rows = self.recommendation_rows()
        if self.active_recommendation_filter != "All Recommendations":
            rows = [r for r in rows if r[1] == self.active_recommendation_filter]
        self.recs_header.setText(f"Recommendations ({len(rows)})")
        self.recs_table.setRowCount(len(rows))
        for r, (title, category, priority, reason, action_text, slot) in enumerate(rows):
            for c, val in enumerate([title, category, priority, reason]):
                self.recs_table.setItem(r, c, QtWidgets.QTableWidgetItem(val))
            btn = QtWidgets.QPushButton(action_text)
            btn.setObjectName("primaryAction")
            btn.setMinimumHeight(36)
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, s=slot: s())
            self.recs_table.setCellWidget(r, 4, btn)

    # ----------------------- Actions -----------------------

    def _popup_style(self):
        return f"""
        QMessageBox {{ background: #ffffff; }}
        QMessageBox QLabel {{ color: {TEXT}; font-family: 'Segoe UI', Arial; font-size: 14px; min-width: 340px; }}
        QMessageBox QPushButton {{ min-width: 90px; min-height: 34px; background: #ffffff; color: {BLUE}; border: 1px solid #bfdbfe; border-radius: 8px; padding: 6px 14px; font-weight: 700; }}
        QMessageBox QPushButton:hover {{ background: #eff6ff; }}
        QMessageBox QPushButton:pressed {{ background: #dbeafe; }}
        """

    def _show_message(self, title, message, icon=QtWidgets.QMessageBox.Icon.Information):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(icon)
        box.setText(message)
        box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        box.setStyleSheet(self._popup_style())
        box.exec()

    def _ask_question(self, title, message):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        box.setText(message)
        box.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
        box.setStyleSheet(self._popup_style())
        return box.exec()

    def mark_action(self, message):
        text = f"{datetime.now().strftime('%I:%M:%S %p')} - {message}"
        self.action_log.insert(0, text)
        if hasattr(self, "action_log_list"):
            self.action_log_list.insertItem(0, text)
        if hasattr(self, "recommendation_status"):
            self.recommendation_status.setText(message)
        if hasattr(self, "quick_action_status"):
            self.quick_action_status.setText(message)

    def action_refresh(self):
        self.refresh_all()
        self.mark_action("Real-time metrics refreshed.")

    def action_smart_scan(self):
        self.refresh_all()
        m = self.current_metrics
        msg = (
            f"Smart Scan Completed\n\n"
            f"Health Score: {m.get('health_score', 0):.1f}/100\n"
            f"CPU: {m.get('cpu_usage', 0):.1f}%\n"
            f"RAM: {m.get('ram_usage', 0):.1f}%\n"
            f"Temperature: {m.get('temperature', 0):.1f}°C\n"
            f"Disk: {m.get('disk_usage', 0):.1f}%"
        )
        self.mark_action("Smart scan completed using live metrics.")
        self._show_message("Smart Scan", msg)

    def temp_dirs(self):
        dirs = [Path(tempfile.gettempdir())]
        if platform.system() == "Windows":
            windir = os.environ.get("WINDIR")
            if windir:
                dirs.append(Path(windir) / "Temp")
        return [d for d in dirs if d.exists()]

    def scan_temp_files(self):
        total = 0
        count = 0
        for folder in self.temp_dirs():
            for p in folder.rglob("*"):
                try:
                    if p.is_file():
                        total += p.stat().st_size
                        count += 1
                except Exception:
                    continue
        return {"files": count, "bytes": total}

    def action_scan_junk(self):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            self.temp_scan_result = self.scan_temp_files()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        mb = self.temp_scan_result["bytes"] / (1024 * 1024)
        if hasattr(self, "junk_value_label"):
            self.junk_value_label.setText(f"{mb:.1f} MB")
        if hasattr(self, "junk_desc_label"):
            self.junk_desc_label.setText(f"{self.temp_scan_result['files']} temporary files found.")
        self.mark_action(f"Temp scan completed: {mb:.1f} MB found.")
        self._show_message("Temp Junk Scan", f"Found {self.temp_scan_result['files']} files\nSize: {mb:.1f} MB\nUse Clean only after reviewing.")

    def action_clean_junk(self):
        if not self.temp_scan_result["files"]:
            self.action_scan_junk()
        reply = self._ask_question(
            "Clean Temp Files",
            "This will delete accessible files from system temp folders. Locked/protected files will be skipped.\n\nContinue?",
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            self.mark_action("Temp cleanup cancelled.")
            return

        deleted_files = 0
        deleted_bytes = 0
        for folder in self.temp_dirs():
            for p in folder.rglob("*"):
                try:
                    if p.is_file():
                        size = p.stat().st_size
                        p.unlink()
                        deleted_files += 1
                        deleted_bytes += size
                except Exception:
                    continue
        mb = deleted_bytes / (1024 * 1024)
        self.temp_scan_result = {"files": 0, "bytes": 0}
        if hasattr(self, "junk_value_label"):
            self.junk_value_label.setText("0 MB")
        self.refresh_all()
        self.mark_action(f"Cleaned {deleted_files} temp files ({mb:.1f} MB).")
        self._show_message("Cleanup Complete", f"Deleted files: {deleted_files}\nReclaimed: {mb:.1f} MB")

    def action_manage_startup(self):
        if platform.system() == "Windows":
            try:
                subprocess.Popen(["taskmgr.exe", "/0", "/startup"])
                self.mark_action("Windows Startup Manager opened.")
                return
            except Exception:
                pass
            try:
                subprocess.Popen(["cmd", "/c", "start", "ms-settings:startupapps"])
                self.mark_action("Windows Startup Apps settings opened.")
                return
            except Exception as exc:
                self._show_message("Startup Manager", f"Could not open Startup Manager:\n{exc}")
                return
        self._show_message("Startup Manager", "Startup manager integration is Windows-specific.")
        self.mark_action("Startup manager is not available on this OS.")

    def action_drive_details(self, name, used, total, free):
        self.mark_action(f"Viewed drive details for {name}.")
        self._show_message("Drive Details", f"Drive: {name}\nUsed: {used}%\nTotal: {total}\nFree: {free}")

    def action_open_system_drive(self):
        root = str(Path.home().anchor or "/")
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", root])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", root])
            else:
                subprocess.Popen(["xdg-open", root])
            self.mark_action("System drive opened.")
        except Exception as exc:
            self._show_message("Open Drive", str(exc))

    def action_manage_large_files(self):
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", "search-ms:query=size:gigantic"])
                self.mark_action("Windows large file search opened.")
            else:
                self._show_message("Large Files", "Use your file manager search for large files on this OS.")
        except Exception as exc:
            self._show_message("Large Files", str(exc))

    def action_uninstaller_tab(self, tab_name):
        self.current_uninstaller_tab=tab_name
        for name,btn in self.uninstaller_tabs.items(): btn.setChecked(name==tab_name)
        if tab_name=="Installed Programs":
            self.installed_title.setText(f"Installed Programs ({len(self.installed_apps)})"); self.app_status_label.setText("Installed software inventory loaded.")
        elif tab_name=="Windows Apps":
            self.action_open_apps_settings(); self.app_status_label.setText("Windows Apps & features settings opened.")
            self.uninstaller_tabs["Installed Programs"].setChecked(True); self.current_uninstaller_tab="Installed Programs"
        else:
            self.action_scan_residual_files(); self.uninstaller_tabs["Installed Programs"].setChecked(True); self.current_uninstaller_tab="Installed Programs"
        self.mark_action(f"{tab_name} selected.")

    def action_scan_residual_files(self):
        if platform.system()!="Windows": self._show_message("Residual Files","Residual-folder review is available on Windows."); return
        roots=[Path(os.environ.get("LOCALAPPDATA","")),Path(os.environ.get("APPDATA","")),Path(os.environ.get("PROGRAMDATA",""))]
        empty=[]
        for root in roots:
            if not root.exists(): continue
            try:
                for child in list(root.iterdir())[:400]:
                    if child.is_dir():
                        try:
                            if not any(child.iterdir()): empty.append(str(child))
                        except Exception: pass
            except Exception: pass
        preview="\n".join(empty[:20]) if empty else "No empty top-level residual folders were found."
        self._show_message("Residual Files Review",f"Safe review completed. The application does not automatically delete program folders.\n\nEmpty folders found: {len(empty)}\n\n{preview}")

    def action_uninstall_app(self, app, confirm=True):
        name=app.get("name","Selected application"); uninstall=app.get("uninstall","")
        if not uninstall:
            self._show_message("Uninstall",f"No registered uninstall command was found for:\n{name}\n\nWindows Apps settings will be opened instead."); self.action_open_apps_settings(); return
        if confirm:
            reply=self._ask_question("Confirm Uninstall",f"Open the official uninstaller for {name}?\n\nNo silent removal is performed. The program's own uninstaller will request final confirmation.")
            if reply!=QtWidgets.QMessageBox.StandardButton.Yes: return
        try:
            cmd=uninstall.strip()
            if cmd.lower().startswith("msiexec") and "/i" in cmd.lower(): cmd=cmd.replace("/I","/X").replace("/i","/x")
            subprocess.Popen(cmd,shell=True); self.mark_action(f"Uninstaller opened for {name}.")
        except Exception as exc: self._show_message("Uninstall",f"Unable to open uninstaller:\n{exc}")

    def action_ai_details(self):
        self.action_smart_scan()

    def action_filter_recommendations(self, name):
        self.active_recommendation_filter = name
        self.populate_recommendations()
        self.mark_action(f"Recommendation filter selected: {name}")

    def action_generate_report(self):
        path = self.write_report("txt")
        self.add_report_row(self.report_combo.currentText(), path)
        self.mark_action("TXT report generated.")
        self._show_message("Report", f"Report generated:\n{path}")

    def action_export_report(self, fmt):
        path = self.write_report(fmt)
        self.add_report_row(self.report_combo.currentText(), path)
        self.mark_action(f"{fmt.upper()} report exported.")
        self._show_message("Export Report", f"{fmt.upper()} report exported:\n{path}")

    def write_report(self, fmt):
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.reports_dir / f"laptop_health_report_{now}.{fmt}"
        metrics = self.current_metrics or self.get_metrics()

        if fmt == "csv":
            with open(base, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                for k, v in metrics.items():
                    writer.writerow([k, v])
        elif fmt == "html":
            rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in metrics.items())
            base.write_text(f"<html><body><h1>Laptop Health Report</h1><table border='1'>{rows}</table></body></html>", encoding="utf-8")
        elif fmt == "pdf":
            try:
                from reportlab.lib.pagesizes import letter
                from reportlab.pdfgen import canvas
                c = canvas.Canvas(str(base), pagesize=letter)
                c.setFont("Helvetica-Bold", 16)
                c.drawString(72, 740, "Laptop Health Report")
                c.setFont("Helvetica", 11)
                y = 700
                for k, v in metrics.items():
                    c.drawString(72, y, f"{k}: {v}")
                    y -= 22
                c.save()
            except Exception:
                base = base.with_suffix(".txt")
                base.write_text(self.report_text(metrics), encoding="utf-8")
        else:
            base.write_text(self.report_text(metrics), encoding="utf-8")
        return str(base)

    def report_text(self, metrics):
        lines = ["Laptop Health Report", f"Generated: {datetime.now()}", ""]
        for k, v in metrics.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def add_report_row(self, report_type, file_path):
        row = self.reports_table.rowCount()
        self.reports_table.insertRow(row)
        self.reports_table.setItem(row, 0, QtWidgets.QTableWidgetItem(report_type))
        self.reports_table.setItem(row, 1, QtWidgets.QTableWidgetItem(datetime.now().strftime("%d-%m-%Y %I:%M %p")))
        self.reports_table.setItem(row, 2, QtWidgets.QTableWidgetItem(file_path))

    def action_save_settings(self):
        self.monitor_interval_value = self.get_monitor_interval()
        self.temp_warning_value = self.get_warning_temp()
        self.temp_critical_value = self.get_critical_temp()
        self._timer.setInterval(self.monitor_interval_value * 1000)
        self.mark_action("Settings saved.")
        QtWidgets.QMessageBox.information(
            self,
            "Settings Saved",
            f"Monitoring interval: {self.monitor_interval_value} seconds\nWarning temperature: {self.temp_warning_value}°C\nCritical temperature: {self.temp_critical_value}°C",
        )

    def get_firewall_status(self):
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-NetFirewallProfile | Select-Object -ExpandProperty Enabled) -join ','"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=5,
                encoding="utf-8",
                errors="ignore",
            )
            return "Active" if "True" in out else "Disabled"
        except Exception:
            return "Unknown"

    def get_system_info_text(self):
        battery = psutil.sensors_battery()
        battery_text = "Not available"
        if battery:
            battery_text = f"{battery.percent}% ({'Plugged in' if battery.power_plugged else 'On battery'})"
        return (
            f"Laptop Health Monitor - Real Time\n\n"
            f"Device: {platform.node()}\n"
            f"Operating System: {platform.platform()}\n"
            f"Processor: {platform.processor()}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"CPU Cores: {psutil.cpu_count(logical=True)}\n"
            f"RAM: {round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB\n"
            f"Disk: {round(psutil.disk_usage(str(Path.home().anchor or '/')).total / (1024 ** 3), 2)} GB\n"
            f"Battery: {battery_text}\n"
            f"Reports folder: {self.reports_dir}"
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.cleanup()
        super().closeEvent(event)
