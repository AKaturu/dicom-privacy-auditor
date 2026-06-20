"""Curated high-signal DICOM privacy rules.

This module intentionally does not claim complete implementation of DICOM PS3.15
Table E.1-1. The standalone auditor surfaces probable risks; the paired comparator
adds source-versus-output checks for remapped UIDs, dates, and unchanged values.
"""

from __future__ import annotations

# Keyword -> (severity, rationale)
DIRECT_IDENTIFIER_KEYWORDS: dict[str, tuple[str, str]] = {
    "PatientName": ("critical", "Direct patient identifier"),
    "PatientID": ("critical", "Patient or medical-record identifier"),
    "OtherPatientIDs": ("critical", "Alternative patient identifier"),
    "OtherPatientNames": ("critical", "Alternative patient name"),
    "PatientBirthDate": ("high", "Patient date of birth"),
    "PatientBirthTime": ("high", "Patient birth time"),
    "PatientAddress": ("critical", "Patient address"),
    "PatientTelephoneNumbers": ("critical", "Patient telephone number"),
    "PatientMotherBirthName": ("critical", "Family-linked identifier"),
    "MedicalRecordLocator": ("critical", "Medical record locator"),
    "ResponsiblePerson": ("high", "Responsible-person identifier"),
    "ResponsiblePersonRole": ("medium", "Responsible-person role"),
    "MilitaryRank": ("medium", "Potential quasi-identifier"),
    "BranchOfService": ("medium", "Potential quasi-identifier"),
    "EthnicGroup": ("medium", "Sensitive demographic attribute"),
    "Occupation": ("medium", "Potential quasi-identifier"),
    "AdditionalPatientHistory": ("high", "Free text may contain identifiers"),
    "ReferringPhysicianName": ("high", "Personnel identifier"),
    "PerformingPhysicianName": ("high", "Personnel identifier"),
    "PhysiciansOfRecord": ("high", "Personnel identifier"),
    "NameOfPhysiciansReadingStudy": ("high", "Personnel identifier"),
    "OperatorsName": ("high", "Personnel identifier"),
    "RequestingPhysician": ("high", "Personnel identifier"),
    "InstitutionName": ("high", "Organization identifier"),
    "InstitutionAddress": ("high", "Organization address"),
    "InstitutionalDepartmentName": ("medium", "Organization identifier"),
    "StationName": ("medium", "Device or location identifier"),
    "DeviceSerialNumber": ("medium", "Device identifier may enable linkage"),
    "AccessionNumber": ("high", "Encounter or order identifier"),
    "StudyID": ("medium", "Study identifier that may permit linkage"),
    "AdmissionID": ("high", "Encounter identifier"),
    "IssuerOfPatientID": ("high", "Identifier namespace"),
    "IssuerOfAdmissionID": ("high", "Encounter identifier namespace"),
    "ClinicalTrialSponsorName": ("medium", "Organization identifier"),
    "ClinicalTrialProtocolID": ("medium", "Protocol identifier"),
    "ClinicalTrialSiteID": ("medium", "Site identifier"),
    "ClinicalTrialSiteName": ("medium", "Site identifier"),
}

FREE_TEXT_KEYWORDS: set[str] = {
    "StudyDescription",
    "SeriesDescription",
    "ProtocolName",
    "ImageComments",
    "DerivationDescription",
    "AcquisitionComments",
    "PatientComments",
    "ReasonForStudy",
    "ReasonForRequestedProcedure",
    "RequestedProcedureDescription",
    "AdmittingDiagnosesDescription",
    "ClinicalTrialProtocolName",
    "ClinicalTrialSiteName",
    "PerformedProcedureStepDescription",
    "ScheduledProcedureStepDescription",
    "InterpretationText",
    "TextValue",
    "ContentDescription",
    "ContentLabel",
}

DATE_TIME_KEYWORDS: set[str] = {
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "ContentDate",
    "InstanceCreationDate",
    "PerformedProcedureStepStartDate",
    "PerformedProcedureStepEndDate",
    "AdmittingDate",
    "StudyTime",
    "SeriesTime",
    "AcquisitionTime",
    "ContentTime",
    "InstanceCreationTime",
    "PerformedProcedureStepStartTime",
    "PerformedProcedureStepEndTime",
    "AdmittingTime",
    "AcquisitionDateTime",
}

# UIDs that identify a class or encoding, not a patient-specific instance.
SAFE_UID_KEYWORDS: set[str] = {
    "SOPClassUID",
    "ReferencedSOPClassUID",
    "MediaStorageSOPClassUID",
    "TransferSyntaxUID",
    "ImplementationClassUID",
    "CodingSchemeUID",
    "ContextGroupExtensionCreatorUID",
}

PIXEL_RISK_FLAGS: dict[str, str] = {
    "BurnedInAnnotation": "Pixel data may contain burned-in annotations",
    "RecognizableVisualFeatures": "Images may contain recognizable visual features",
}

GRAPHIC_OR_EMBEDDED_KEYWORDS: dict[str, tuple[str, str]] = {
    "OverlayData": ("high", "Overlay data may contain identifying graphics or text"),
    "CurveData": ("high", "Curve data may contain identifying information"),
    "EncapsulatedDocument": ("critical", "Encapsulated content requires content-specific de-identification"),
    "SpectroscopyData": ("medium", "Non-image bulk data requires object-specific review"),
    "OriginalAttributesSequence": ("critical", "May contain unencrypted copies of modified attributes"),
    "EncryptedAttributesSequence": (
        "high",
        "Encrypted identity-recovery content requires key-governance review",
    ),
    "DigitalSignaturesSequence": ("high", "Digital signatures may include signer identity"),
}
