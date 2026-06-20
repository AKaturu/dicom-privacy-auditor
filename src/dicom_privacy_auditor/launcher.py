"""Unified command-line launcher for frozen and installed distributions."""

from __future__ import annotations

import sys
from collections.abc import Callable

from . import __version__


def _usage() -> str:
    return f"""DICOM Privacy Auditor {__version__}

Usage:
  dicom-privacy <command> [arguments]

Commands:
  audit        Audit a DICOM file or directory for privacy risks
  compare      Compare a source DICOM object with a candidate output
  deidentify   Run the transparent research baseline on one object
  benchmark    Generate, run, evaluate, plot, or compare benchmarks
  ps315        Prepare/query/evaluate user-local DICOM PS3.15 profile rules
  midi         Import and evaluate the public MIDI-B benchmark
  adapter      Run Orthanc or RSNA external-tool adapters
  review       Human pixel/metadata adjudication workstation
  iod          Prepare/query a user-local PS3.3 IOD registry
  corpus       Evaluate corpus-level UID/date/pseudonym consistency
  dicomweb     QIDO-RS/WADO-RS/STOW-RS client
  study        Atomic local or DICOMweb study processing
  campaign     Run complete MIDI-B live-tool campaigns
  external     Check external-validation resources and provenance locks
  demo         Generate a complete synthetic demonstration package
  report       Generate manuscript-ready tables and templates
  desktop      Open the graphical desktop auditor
  version      Print the application version

Examples:
  dicom-privacy audit sample_data --json audit.json
  dicom-privacy compare source.dcm candidate.dcm
  dicom-privacy benchmark all workspace --pipeline baseline --overwrite

Run "dicom-privacy <command> --help" for command-specific options.
"""


def _commands() -> dict[str, Callable[[list[str] | None], int]]:
    # Explicit imports allow PyInstaller to discover every command module.
    from .adapter_cli import main as adapter_main
    from .benchmark_cli import main as benchmark_main
    from .campaign.cli import main as campaign_main
    from .cli import main as audit_main
    from .compare_cli import main as compare_main
    from .corpus.cli import main as corpus_main
    from .deidentify_cli import main as deidentify_main
    from .demo import main as demo_main
    from .dicomweb.cli import main as dicomweb_main
    from .external_validation import main as external_main
    from .iod.cli import main as iod_main
    from .midi_cli import main as midi_main
    from .ps315.cli import main as ps315_main
    from .publication.cli import main as report_main
    from .review_cli import main as review_main
    from .study.cli import main as study_main

    return {
        "audit": audit_main,
        "compare": compare_main,
        "deidentify": deidentify_main,
        "benchmark": benchmark_main,
        "ps315": ps315_main,
        "midi": midi_main,
        "adapter": adapter_main,
        "review": review_main,
        "iod": iod_main,
        "corpus": corpus_main,
        "dicomweb": dicomweb_main,
        "study": study_main,
        "campaign": campaign_main,
        "external": external_main,
        "demo": demo_main,
        "report": report_main,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(_usage())
        return 0
    if args[0] in {"-V", "--version", "version"}:
        print(__version__)
        return 0
    if args[0] == "desktop":
        # The dedicated native CLI intentionally excludes Tk to keep the
        # executable smaller and avoid duplicating the desktop runtime.  An
        # installed Python package can still launch the desktop subcommand.
        executable_name = str(getattr(sys, "executable", "")).casefold()
        if getattr(sys, "frozen", False) and "dicomprivacyauditor-cli" in executable_name:
            print(
                "The native CLI build does not embed the desktop runtime. "
                "Launch the DICOMPrivacyAuditor desktop executable instead.",
                file=sys.stderr,
            )
            return 2

        from .desktop import main as desktop_main

        return desktop_main(args[1:])

    command = _commands().get(args[0])
    if command is None:
        print(f"Unknown command: {args[0]}\n", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    return command(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
