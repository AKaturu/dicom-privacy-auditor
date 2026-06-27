from __future__ import annotations

import hashlib
import random
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, ExplicitVRLittleEndian, SecondaryCaptureImageStorage

from dicom_privacy_auditor import __version__

from .manifest import MANIFEST_VERSION, BenchmarkManifest, CaseRecord, Injection

STRATA = (
    "standard_metadata",
    "nested_sequence",
    "private_attribute",
    "free_text",
    "filename",
    "temporal",
    "uid",
    "pixel_annotation",
    "overlay_graphics",
    "file_meta",
    "preamble",
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def deterministic_uid(namespace: str) -> str:
    return f"2.25.{uuid.uuid5(uuid.NAMESPACE_URL, namespace).int}"


def _synthetic_token(case_index: int, kind: str) -> str:
    values = {
        "name": f"SYNTHETIC{case_index:04d}^PERSON",
        "patient_id": f"SYN-MRN-{case_index:06d}",
        "accession": f"SYN-ACC-{case_index:06d}",
        "email": f"synthetic{case_index:04d}@example.invalid",
        "phone": f"919-555-{case_index % 10000:04d}",
        "address": f"{100 + case_index} SYNTHETIC AVENUE^^TESTVILLE^NC^00000",
        "institution": f"SYNTHETIC MEDICAL CENTER {case_index:04d}",
        "physician": f"SYNDOCTOR{case_index:04d}^TEST",
        "date": f"{1980 + case_index % 30:04d}{1 + case_index % 12:02d}{1 + case_index % 27:02d}",
        "uid": deterministic_uid(f"injected:{case_index}"),
        "private": f"SYNTHETIC PRIVATE ROUTING {case_index:04d}",
        "pixel": f"SYN-MRN-{case_index:06d}",
        "overlay": f"SYN-OVERLAY-{case_index:06d}",
        "aet": f"SYN_AET_{case_index:04d}",
        "preamble": f"SYNTHETIC-PREAMBLE-{case_index:04d}",
    }
    return values[kind]


def _base_pixels(width: int = 256, height: int = 128) -> np.ndarray:
    x = np.linspace(20, 80, width, dtype=np.float32)
    y = np.linspace(0, 15, height, dtype=np.float32)[:, None]
    image = x[None, :] + y
    return np.clip(image, 0, 255).astype(np.uint8)


def base_dataset(path: Path, case_id: str) -> FileDataset:
    sop_instance_uid = deterministic_uid(f"{case_id}:sop")
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = UID(sop_instance_uid)
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = UID(deterministic_uid("dicom-privacy-auditor:implementation"))
    file_meta.ImplementationVersionName = "DPA_BENCH_020"

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop_instance_uid
    ds.StudyInstanceUID = deterministic_uid(f"{case_id}:study")
    ds.SeriesInstanceUID = deterministic_uid(f"{case_id}:series")
    ds.FrameOfReferenceUID = deterministic_uid(f"{case_id}:frame")
    ds.Modality = "OT"
    ds.InstanceNumber = 1
    pixels = _base_pixels()
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = pixels.tobytes()
    ds.BurnedInAnnotation = "NO"
    ds.RecognizableVisualFeatures = "NO"
    return ds


def _required_element(dataset: Dataset, keyword: str):
    element = dataset.data_element(keyword)
    if element is None:
        raise RuntimeError(f"Synthetic injection failed to create {keyword}")
    return element


def _injection(
    case_id: str,
    stratum: str,
    location_kind: str,
    path: str,
    value: str,
    *,
    keyword: str | None = None,
    tag: str | None = None,
    bbox: tuple[int, int, int, int] | None = None,
    description: str | None = None,
) -> Injection:
    return Injection(
        injection_id=f"{case_id}:{stratum}:001",
        stratum=stratum,
        location_kind=location_kind,
        path=path,
        value=value,
        value_sha256=_hash(value),
        keyword=keyword,
        tag=tag,
        bbox_xyxy=bbox,
        description=description,
    )


def _inject_standard(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    choices: list[tuple[str, str, str]] = [
        ("PatientName", "name", "root/PatientName"),
        ("PatientID", "patient_id", "root/PatientID"),
        ("AccessionNumber", "accession", "root/AccessionNumber"),
        ("PatientAddress", "address", "root/PatientAddress"),
        ("InstitutionName", "institution", "root/InstitutionName"),
        ("ReferringPhysicianName", "physician", "root/ReferringPhysicianName"),
    ]
    keyword, kind, path = choices[variant % len(choices)]
    value = _synthetic_token(index, kind)
    setattr(ds, keyword, value)
    element = _required_element(ds, keyword)
    return _injection(
        case_id, "standard_metadata", "dicom_element", path, value, keyword=keyword, tag=str(element.tag)
    )


def _inject_nested(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    item = Dataset()
    if variant % 2 == 0:
        value = f"PATIENT ID: {_synthetic_token(index, 'patient_id')}"
        item.RequestedProcedureDescription = value
        keyword = "RequestedProcedureDescription"
        path = "root/RequestAttributesSequence[0]/RequestedProcedureDescription"
    else:
        value = _synthetic_token(index, "physician")
        item.RequestingPhysician = value
        keyword = "RequestingPhysician"
        path = "root/RequestAttributesSequence[0]/RequestingPhysician"
    ds.RequestAttributesSequence = Sequence([item])
    element = _required_element(item, keyword)
    return _injection(
        case_id, "nested_sequence", "dicom_element", path, value, keyword=keyword, tag=str(element.tag)
    )


def _inject_private(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    value = _synthetic_token(index, "private")
    creator = f"SYNTHETIC_CREATOR_{variant:02d}"
    block = ds.private_block(0x0011, creator, create=True)
    block.add_new(0x01, "LO", value)
    tag = block.get_tag(0x01)
    return _injection(
        case_id,
        "private_attribute",
        "private_element",
        f"root/({tag.group:04X},{tag.element:04X})",
        value,
        tag=f"({tag.group:04X},{tag.element:04X})",
        description=f"Private creator: {creator}",
    )


def _inject_free_text(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    choices = [
        ("StudyDescription", f"RESEARCH CASE; EMAIL {_synthetic_token(index, 'email')}"),
        ("SeriesDescription", f"CALL {_synthetic_token(index, 'phone')} FOR PATIENT"),
        ("ProtocolName", f"MRN: {_synthetic_token(index, 'patient_id')}"),
        ("ImageComments", f"PATIENT: {_synthetic_token(index, 'name')}"),
    ]
    keyword, value = choices[variant % len(choices)]
    setattr(ds, keyword, value)
    element = _required_element(ds, keyword)
    return _injection(
        case_id,
        "free_text",
        "dicom_element",
        f"root/{keyword}",
        value,
        keyword=keyword,
        tag=str(element.tag),
    )


def _inject_filename(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    value = _synthetic_token(index, "name").replace("^", "_")
    return _injection(
        case_id,
        "filename",
        "filename",
        "filesystem/filename",
        value,
        description="Artificial name token in filename",
    )


def _inject_temporal(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    choices = ["StudyDate", "SeriesDate", "AcquisitionDate", "ContentDate"]
    keyword = choices[variant % len(choices)]
    value = _synthetic_token(index, "date")
    setattr(ds, keyword, value)
    element = _required_element(ds, keyword)
    return _injection(
        case_id, "temporal", "dicom_element", f"root/{keyword}", value, keyword=keyword, tag=str(element.tag)
    )


def _inject_uid(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    choices = ["StudyInstanceUID", "SeriesInstanceUID", "FrameOfReferenceUID", "SOPInstanceUID"]
    keyword = choices[variant % len(choices)]
    value = _synthetic_token(index, "uid")
    setattr(ds, keyword, value)
    if keyword == "SOPInstanceUID":
        ds.file_meta.MediaStorageSOPInstanceUID = UID(value)
    element = _required_element(ds, keyword)
    return _injection(
        case_id, "uid", "dicom_element", f"root/{keyword}", value, keyword=keyword, tag=str(element.tag)
    )


def _inject_pixel(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    value = _synthetic_token(index, "pixel")
    image = Image.fromarray(np.asarray(ds.pixel_array).astype(np.uint8), mode="L")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:  # older Pillow
        font = ImageFont.load_default()
    x, y = (8, 8) if variant % 2 == 0 else (8, ds.Rows - 28)
    bbox = draw.textbbox((x, y), value, font=font, stroke_width=1)
    draw.rectangle((bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2), fill=0)
    draw.text((x, y), value, fill=255, font=font, stroke_width=1, stroke_fill=255)
    array = np.asarray(image, dtype=np.uint8)
    ds.PixelData = array.tobytes()
    ds.BurnedInAnnotation = "YES"
    expanded = (
        max(0, int(bbox[0]) - 2),
        max(0, int(bbox[1]) - 2),
        min(int(ds.Columns), int(bbox[2]) + 2),
        min(int(ds.Rows), int(bbox[3]) + 2),
    )
    return _injection(
        case_id,
        "pixel_annotation",
        "pixel_bbox",
        "root/PixelData",
        value,
        keyword="PixelData",
        tag="(7FE0,0010)",
        bbox=expanded,
    )


def _inject_overlay_graphics(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    value = _synthetic_token(index, "overlay")
    group = 0x6000
    ds.add_new((group, 0x0010), "US", int(ds.Rows))
    ds.add_new((group, 0x0011), "US", int(ds.Columns))
    ds.add_new((group, 0x0040), "CS", "G")
    ds.add_new((group, 0x0050), "SS", [1, 1])
    ds.add_new((group, 0x0100), "US", 1)
    ds.add_new((group, 0x0102), "US", 0)
    ds.add_new((group, 0x1500), "LO", f"Synthetic overlay label {index:04d}")
    ds.add_new((group, 0x3000), "OW", value.encode("ascii") + b"\0" * 16)
    return _injection(
        case_id,
        "overlay_graphics",
        "overlay_data",
        "root/OverlayData",
        value,
        keyword="OverlayData",
        tag="(6000,3000)",
        description="Artificial identifier in overlay graphics bulk data",
    )


def _inject_file_meta(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    value = _synthetic_token(index, "aet")
    ds.file_meta.SourceApplicationEntityTitle = value
    return _injection(
        case_id,
        "file_meta",
        "file_meta_element",
        "file_meta/SourceApplicationEntityTitle",
        value,
        keyword="SourceApplicationEntityTitle",
        tag="(0002,0016)",
    )


def _inject_preamble(ds: FileDataset, case_id: str, index: int, variant: int) -> Injection:
    value = _synthetic_token(index, "preamble")
    payload = value.encode("ascii")[:128]
    ds.preamble = payload + b"\0" * (128 - len(payload))
    return _injection(
        case_id,
        "preamble",
        "preamble",
        "preamble",
        value,
        description="Artificial identifier in 128-byte preamble",
    )


INJECTORS: dict[str, Callable[[FileDataset, str, int, int], Injection]] = {
    "standard_metadata": _inject_standard,
    "nested_sequence": _inject_nested,
    "private_attribute": _inject_private,
    "free_text": _inject_free_text,
    "filename": _inject_filename,
    "temporal": _inject_temporal,
    "uid": _inject_uid,
    "pixel_annotation": _inject_pixel,
    "overlay_graphics": _inject_overlay_graphics,
    "file_meta": _inject_file_meta,
    "preamble": _inject_preamble,
}


def generate_benchmark(
    output_dir: str | Path,
    *,
    cases_per_stratum: int = 5,
    clean_controls: int = 10,
    seed: int = 20260619,
    overwrite: bool = False,
) -> BenchmarkManifest:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output}")
        shutil.rmtree(output)
    objects_dir = output / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    cases: list[CaseRecord] = []
    case_index = 0

    schedule = [(stratum, variant) for stratum in STRATA for variant in range(cases_per_stratum)]
    rng.shuffle(schedule)
    for stratum, variant in schedule:
        case_index += 1
        case_id = f"case-{case_index:05d}"
        placeholder = objects_dir / f"{case_id}.dcm"
        ds = base_dataset(placeholder, case_id)
        injection = INJECTORS[stratum](ds, case_id, case_index, variant)
        if stratum == "filename":
            filename = f"{injection.value}_{case_id}.dcm"
        else:
            filename = f"{case_id}.dcm"
        relative_path = (Path("objects") / filename).as_posix()
        target = output / relative_path
        ds.filename = str(target)
        ds.save_as(target, enforce_file_format=True)
        cases.append(
            CaseRecord(
                case_id=case_id,
                relative_path=relative_path,
                modality=str(ds.Modality),
                clean_control=False,
                injections=[injection],
                metadata={"stratum": stratum, "variant": variant},
            )
        )

    for control_index in range(clean_controls):
        case_index += 1
        case_id = f"control-{control_index + 1:05d}"
        relative_path = (Path("objects") / f"{case_id}.dcm").as_posix()
        target = output / relative_path
        ds = base_dataset(target, case_id)
        ds.PatientName = ""
        ds.PatientID = ""
        ds.PatientIdentityRemoved = "YES"
        ds.DeidentificationMethod = "Synthetic clean control; no identifier injected"
        ds.LongitudinalTemporalInformationModified = "REMOVED"
        ds.BurnedInAnnotation = "NO"
        ds.RecognizableVisualFeatures = "NO"
        ds.save_as(target, enforce_file_format=True)
        cases.append(
            CaseRecord(
                case_id=case_id,
                relative_path=relative_path,
                modality=str(ds.Modality),
                clean_control=True,
                injections=[],
                metadata={"control_index": control_index},
            )
        )

    manifest = BenchmarkManifest(
        benchmark_name="DICOM Privacy Auditor Synthetic Benchmark",
        version=__version__,
        manifest_version=MANIFEST_VERSION,
        seed=seed,
        standard_reference="DICOM PS3.15 2026c Attribute Confidentiality Profiles",
        cases=cases,
        metadata={
            "cases_per_stratum": cases_per_stratum,
            "clean_controls": clean_controls,
            "strata": list(STRATA),
            "contains_real_phi": False,
        },
    )
    manifest.write(output / "manifest.json")
    return manifest
