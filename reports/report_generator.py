import csv
import html
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


class ReportGenerator:
    def __init__(self, output_dir: str | None = None) -> None:
        self.output_dir = Path(output_dir or os.path.join(os.path.dirname(__file__), "output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, report_type: str, metrics: List[dict[str, Any]]) -> str:
        file_name = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        pdf_path = self.output_dir / f"{file_name}.pdf"
        excel_path = self.output_dir / f"{file_name}.xlsx"
        html_path = self.output_dir / f"{file_name}.html"
        csv_path = self.output_dir / f"{file_name}.csv"
        self._generate_pdf(pdf_path, report_type, metrics)
        self._generate_excel(excel_path, report_type, metrics)
        self._generate_html(html_path, report_type, metrics)
        self._generate_csv(csv_path, report_type, metrics)
        return str(pdf_path)

    def _generate_pdf(self, path: Path, report_type: str, metrics: List[dict[str, Any]]) -> None:
        pdf = canvas.Canvas(str(path), pagesize=letter)
        pdf.setTitle(report_type)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, 760, f"Laptop Health {report_type.capitalize()} Report")
        pdf.setFont("Helvetica", 11)
        y = 730
        for metric in metrics[-10:]:
            pdf.drawString(50, y, f"{metric.get('timestamp', '')} | CPU {metric.get('cpu_usage')} | RAM {metric.get('ram_usage')} | Temp {metric.get('temperature')} | Health {metric.get('health_score')}")
            y -= 14
        pdf.save()

    def _generate_excel(self, path: Path, report_type: str, metrics: List[dict[str, Any]]) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = report_type
        sheet.append(["timestamp", "cpu_usage", "ram_usage", "battery_health", "temperature", "disk_usage", "network_usage", "health_score"])
        for metric in metrics:
            sheet.append([
                metric.get("timestamp", ""),
                metric.get("cpu_usage", 0),
                metric.get("ram_usage", 0),
                metric.get("battery_health", 0),
                metric.get("temperature", 0),
                metric.get("disk_usage", 0),
                metric.get("network_usage", 0),
                metric.get("health_score", 0),
            ])
        workbook.save(path)

    def _generate_html(self, path: Path, report_type: str, metrics: List[dict[str, Any]]) -> None:
        rows = "".join(
            f"<tr><td>{html.escape(str(metric.get('timestamp', '')))}</td><td>{metric.get('cpu_usage', 0)}</td><td>{metric.get('ram_usage', 0)}</td><td>{metric.get('temperature', 0)}</td><td>{metric.get('health_score', 0)}</td></tr>"
            for metric in metrics[-10:]
        )
        content = f"""<!DOCTYPE html><html><body><h1>{html.escape(report_type)} Report</h1><table><tr><th>Timestamp</th><th>CPU</th><th>RAM</th><th>Temperature</th><th>Health</th></tr>{rows}</table></body></html>"""
        path.write_text(content, encoding="utf-8")

    def _generate_csv(self, path: Path, report_type: str, metrics: List[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "cpu_usage", "ram_usage", "battery_health", "temperature", "disk_usage", "network_usage", "health_score"])
            for metric in metrics:
                writer.writerow([
                    metric.get("timestamp", ""),
                    metric.get("cpu_usage", 0),
                    metric.get("ram_usage", 0),
                    metric.get("battery_health", 0),
                    metric.get("temperature", 0),
                    metric.get("disk_usage", 0),
                    metric.get("network_usage", 0),
                    metric.get("health_score", 0),
                ])
