DICOM Privacy Auditor — Native Release
======================================

Contents
--------
DICOMPrivacyAuditor
    Double-click graphical auditor. It saves privacy-safe JSON and CSV reports.

DICOMPrivacyAuditor-CLI
    Terminal executable containing audit, compare, deidentify, benchmark, PS3.15, MIDI-B, adapter, review-database, IOD, corpus, DICOMweb, study, and campaign commands.

CLI examples
------------
Windows PowerShell:
  .\DICOMPrivacyAuditor-CLI.exe audit C:\path\to\dicoms --json audit.json --csv audit.csv

macOS/Linux:
  ./DICOMPrivacyAuditor-CLI audit /path/to/dicoms --json audit.json --csv audit.csv

Help:
  DICOMPrivacyAuditor-CLI --help
  DICOMPrivacyAuditor-CLI audit --help
  DICOMPrivacyAuditor-CLI ps315 info --json
  DICOMPrivacyAuditor-CLI midi --help
  DICOMPrivacyAuditor-CLI adapter --help
  DICOMPrivacyAuditor-CLI review --help
  DICOMPrivacyAuditor-CLI iod --help
  DICOMPrivacyAuditor-CLI corpus --help
  DICOMPrivacyAuditor-CLI dicomweb --help
  DICOMPrivacyAuditor-CLI study --help
  DICOMPrivacyAuditor-CLI campaign --help
  DICOMPrivacyAuditor-CLI external --help
  DICOMPrivacyAuditor-CLI report --help
  DICOMPrivacyAuditor-CLI demo --help

The browser-based Streamlit review workstation requires the Python UI installation;
the native CLI supports review database creation, integrity checks, summary, agreement, disagreement/adjudication packets, and export.
Native binaries omit optional PNG plotting. JSON, CSV, and Markdown benchmark outputs remain available.

Safety
------
This is a research prototype, not a DICOM PS3.15/HIPAA/GDPR compliance certificate.
Zero findings do not prove that an object is safe to release. The desktop interface
redacts source paths and DICOM values by default. Treat reports as potentially sensitive.

The baseline de-identifier is a transparent benchmark control, not a production
clinical de-identification engine.

LEGAL NOTICE
------------
DICOM® is the registered trademark of the National Electrical Manufacturers Association for its standards publications relating to digital communications of medical information, all rights reserved. This independent project is not endorsed or certified by NEMA or the DICOM Standards Committee. No DICOM Standard document or complete extracted standards table is bundled with these executables.
