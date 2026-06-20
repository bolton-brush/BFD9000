"""Shared code systems and identifier system URLs."""

SYSTEM_RECORD_TYPE = "https://orthodontics.case.edu/fhir/identifier-system/record-type"
SYSTEM_ORIENTATION = "http://snomed.info/sct"
SYSTEM_MODALITY = "http://dicom.nema.org/resources/ontology/DCM"
SYSTEM_PROCEDURE = "http://snomed.info/sct"
SYSTEM_BODY_SITE = "http://snomed.info/sct"
SYSTEM_IDENTIFIER_BOLTON_SUBJECT = (
    "https://orthodontics.case.edu/fhir/identifier-system/bolton-subject-id"
)
SYSTEM_IDENTIFIER_BRUSH = (
    "https://orthodontics.case.edu/fhir/identifier-system/brush-id"
)
SYSTEM_IDENTIFIER_LANCASTER_SUBJECT = (
    "https://cleftclinic.org/fhir/identifier-system/lancaster-subject-id"
)
SYSTEM_IDENTIFIER_RICHARDSON_SUBJECT = (
    "https://orthodontics.case.edu/fhir/identifier-system/richardson-subject-id"
)
SYSTEM_IDENTIFIER_RICHARDSON_OLD = (
    "https://orthodontics.case.edu/fhir/identifier-system/richardson-old-id"
)
SYSTEM_IDENTIFIER_IMAGE_TYPE = (
    "https://orthodontics.case.edu/fhir/identifier-system/image-type"
)
SYSTEM_IDENTIFIER_BOLTON_PHYSICAL_RECORD = (
    "https://orthodontics.case.edu/fhir/identifier-system/bolton-physical-record-id"
)
SYSTEM_IDENTIFIER_BOLTON_DIGITAL_RECORD = (
    "https://orthodontics.case.edu/fhir/identifier-system/bolton-digital-record-id"
)

RECORD_TYPE_MODALITY_MAP = {
    # Map CWRU record type codes to DICOM modality codes.
    # Used when creating records if modality is not supplied.
    # Update this if new record types are added or modality rules change.
    "L": "RG",
    "F": "RG",
    "P": "RG",
    "FA": "RG",
    "H": "RG",
    "CS": "RG",
    "E": "RG",
    "K": "RG",
    "RE": "DOCD",
    "RF": "DOCD",
    "SM": "OSS",
    "SU": "OSS",
    "SL": "OSS",
    "FM": "OSS",
}

VALUESET_EXPAND_URLS = {
    # FHIR $expand endpoints used by import_valuesets.
    # Update when valueset locations move or new valuesets are added.
    "record_types": "http://terminology.open-ortho.org/fhir/cwru-ortho-record-types/$expand",
}

BFD9000_ROOT_UID = "1.3.6.1.4.1.61741.11.8"
STUDYINSTANCEUID_ROOT = f"{BFD9000_ROOT_UID}.2"
SERIESINSTANCEUID_ROOT = f"{BFD9000_ROOT_UID}.3"
SOPINSTANCEUID_ROOT = f"{BFD9000_ROOT_UID}.4"

EXT_TO_MIMES: dict[tuple[str, ...], tuple[str, ...]] = {
    ("png",): ("image/png",),
    ("tif", "tiff"): ("image/tiff",),
    ("stl",): (
        "application/octet-stream",
        "model/stl",
        "text/plain",
    ),
}
