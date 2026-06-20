"""Tk desktop interface for privacy-safe DICOM auditing."""

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .audit import audit_path
from .export import write_csv, write_json
from .models import AuditReport


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _severity_rank(value: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(value, 0)


class DesktopApplication:
    def __init__(self, root: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.root.title(f"DICOM Privacy Auditor {__version__}")
        self.root.minsize(900, 620)
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.reports: list[AuditReport] = []
        self.output_dir: Path | None = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.home() / "DICOM-Privacy-Audit-Reports"))
        self.pixel_var = tk.BooleanVar(value=False)
        self.uid_var = tk.BooleanVar(value=False)
        self.date_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Choose a DICOM file or directory to begin.")
        self.summary_var = tk.StringVar(value="No audit has been run.")

        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="DICOM Privacy Auditor", font=("TkDefaultFont", 17, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Research prototype. Reports redact source paths and DICOM values by default. "
                "A clean report is not proof that a file is safe to release."
            ),
            wraplength=850,
        ).pack(anchor="w", pady=(2, 12))

        input_frame = ttk.LabelFrame(outer, text="Input and reports", padding=10)
        input_frame.pack(fill="x")
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="DICOM input").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(input_frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(input_frame, text="Choose file", command=self.choose_file).grid(
            row=0, column=2, padx=4, pady=4
        )
        ttk.Button(input_frame, text="Choose folder", command=self.choose_folder).grid(
            row=0, column=3, pady=4
        )

        ttk.Label(input_frame, text="Report folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(input_frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(input_frame, text="Choose folder", command=self.choose_output).grid(
            row=1, column=2, padx=4, pady=4
        )
        self.open_button = ttk.Button(
            input_frame, text="Open reports", command=self.open_reports, state="disabled"
        )
        self.open_button.grid(row=1, column=3, pady=4)

        options = ttk.LabelFrame(outer, text="Audit options", padding=10)
        options.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(options, text="Review dates and times", variable=self.date_var).pack(
            side="left", padx=(0, 16)
        )
        ttk.Checkbutton(options, text="Review instance UIDs", variable=self.uid_var).pack(
            side="left", padx=(0, 16)
        )
        ttk.Checkbutton(options, text="Experimental pixel-border scan", variable=self.pixel_var).pack(
            side="left", padx=(0, 16)
        )
        ttk.Checkbutton(options, text="Force non-Part-10 parsing", variable=self.force_var).pack(side="left")

        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=10)
        self.run_button = ttk.Button(action_row, text="Run privacy audit", command=self.start_audit)
        self.run_button.pack(side="left")
        self.progress = ttk.Progressbar(action_row, mode="indeterminate", length=220)
        self.progress.pack(side="left", padx=12)
        ttk.Label(action_row, textvariable=self.status_var).pack(side="left", fill="x", expand=True)

        ttk.Label(outer, textvariable=self.summary_var, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="both", expand=True, pady=(6, 0))
        columns = ("source", "readable", "findings", "severity", "risk")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=11)
        headings = {
            "source": "Privacy-safe source ID",
            "readable": "Readable",
            "findings": "Findings",
            "severity": "Highest severity",
            "risk": "Risk score",
        }
        widths = {"source": 360, "readable": 80, "findings": 85, "severity": 125, "risk": 85}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], anchor="center" if column != "source" else "w")
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind("<<TreeviewSelect>>", self.show_selected)

        details_frame = ttk.LabelFrame(outer, text="Selected file findings", padding=6)
        details_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.details = tk.Text(details_frame, height=9, wrap="word", state="disabled")
        self.details.pack(fill="both", expand=True)

        self.root.after(100, self.poll_events)

    def choose_file(self) -> None:
        from tkinter import filedialog

        value = filedialog.askopenfilename(
            title="Choose a DICOM file", filetypes=[("DICOM or all files", "*.*")]
        )
        if value:
            self.input_var.set(value)

    def choose_folder(self) -> None:
        from tkinter import filedialog

        value = filedialog.askdirectory(title="Choose a directory containing DICOM files")
        if value:
            self.input_var.set(value)

    def choose_output(self) -> None:
        from tkinter import filedialog

        value = filedialog.askdirectory(title="Choose a report directory")
        if value:
            self.output_var.set(value)

    def start_audit(self) -> None:
        from tkinter import messagebox

        source = Path(self.input_var.get()).expanduser()
        if not source.exists():
            messagebox.showerror("Input not found", "Choose an existing DICOM file or directory.")
            return
        output = Path(self.output_var.get()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Cannot create report folder", str(exc))
            return

        self.run_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.progress.start(10)
        self.status_var.set("Auditing files…")
        self.summary_var.set("Audit in progress.")
        self._clear_results()

        settings = {
            "source": source,
            "output": output,
            "include_dates": self.date_var.get(),
            "include_uid_review": self.uid_var.get(),
            "inspect_pixels": self.pixel_var.get(),
            "force": self.force_var.get(),
        }
        threading.Thread(target=self._audit_worker, args=(settings,), daemon=True).start()

    def _audit_worker(self, settings: dict[str, Any]) -> None:
        try:
            reports = audit_path(
                settings["source"],
                force=settings["force"],
                include_dates=settings["include_dates"],
                include_uid_review=settings["include_uid_review"],
                inspect_pixels=settings["inspect_pixels"],
                show_values=False,
                show_source_paths=False,
            )
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            json_path = settings["output"] / f"dicom-privacy-audit-{timestamp}.json"
            csv_path = settings["output"] / f"dicom-privacy-audit-{timestamp}.csv"
            write_json(reports, json_path)
            write_csv(reports, csv_path)
            self.events.put(("done", (reports, settings["output"], json_path, csv_path)))
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))

    def poll_events(self) -> None:
        from tkinter import messagebox

        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "done":
                    reports, output, json_path, csv_path = payload
                    self.finish_audit(reports, output, json_path, csv_path)
                elif kind == "error":
                    self.progress.stop()
                    self.run_button.configure(state="normal")
                    self.status_var.set("Audit failed.")
                    messagebox.showerror("Audit failed", payload)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def finish_audit(self, reports: list[AuditReport], output: Path, json_path: Path, csv_path: Path) -> None:
        self.reports = reports
        self.output_dir = output
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.open_button.configure(state="normal")

        readable = sum(report.readable for report in reports)
        findings = sum(report.finding_count for report in reports)
        highest = max((report.highest_severity for report in reports), key=_severity_rank, default="info")
        self.summary_var.set(
            f"Files: {len(reports)}  |  Readable: {readable}  |  Findings: {findings}  |  Highest: {highest}"
        )
        self.status_var.set(f"Saved {json_path.name} and {csv_path.name}")

        for index, report in enumerate(reports):
            source = report.source_id or report.source
            self.table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    source,
                    "Yes" if report.readable else "No",
                    report.finding_count,
                    report.highest_severity,
                    report.risk_score,
                ),
            )
        if reports:
            self.table.selection_set("0")
            self.table.focus("0")
            self.show_selected()

    def show_selected(self, _event: Any = None) -> None:
        selection = self.table.selection()
        if not selection:
            return
        report = self.reports[int(selection[0])]
        lines = [
            f"Source ID: {report.source_id or report.source}",
            f"Readable: {report.readable}",
            f"Modality: {report.modality or 'unknown'}",
            f"Risk score: {report.risk_score}",
            "",
        ]
        if report.error:
            lines.append(f"Error: {report.error}")
        elif not report.findings:
            lines.append(
                "No findings were produced. This does not establish that the object is de-identified."
            )
        else:
            for finding in report.findings:
                location = f" ({finding.path})" if finding.path else ""
                lines.append(f"[{finding.severity.upper()}] {finding.code}{location}")
                lines.append(f"  {finding.message}")
                if finding.recommendation:
                    lines.append(f"  Recommendation: {finding.recommendation}")
                if finding.value_preview:
                    lines.append(f"  Evidence: {finding.value_preview}")
                lines.append("")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")

    def _clear_results(self) -> None:
        self.reports = []
        for item in self.table.get_children():
            self.table.delete(item)
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.configure(state="disabled")

    def open_reports(self) -> None:
        if self.output_dir is not None:
            _open_folder(self.output_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open the DICOM Privacy Auditor desktop interface.")
    parser.add_argument("path", nargs="?", type=Path, help="Optional DICOM file or folder to preselect")
    parser.add_argument("--version", action="store_true", help="Print the application version and exit")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Verify that the packaged GUI runtime can import Tk and exit without opening a window",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        print(f"Tk desktop support is unavailable: {exc}", file=sys.stderr)
        return 1
    if args.self_check:
        print(f"DICOM Privacy Auditor {__version__}: desktop runtime OK")
        return 0

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Cannot start the desktop interface: {exc}", file=sys.stderr)
        return 1
    app = DesktopApplication(root)
    if args.path:
        app.input_var.set(str(args.path))
    try:
        root.mainloop()
    except Exception as exc:  # pragma: no cover - top-level GUI safety net
        messagebox.showerror("Unexpected error", f"{type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
