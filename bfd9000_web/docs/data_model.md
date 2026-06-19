# Archive Data Model

This document defines the archive concepts and rationale used by the Django models.

- [Archive Data Model](#archive-data-model)
  - [Core hierarchy](#core-hierarchy)
  - [Models](#models)
    - [Subject](#subject)
    - [Encounter](#encounter)
      - [Encounter Date](#encounter-date)
      - [Encounter Age](#encounter-age)
    - [ImagingStudy](#imagingstudy)
    - [Series](#series)
    - [PhysicalRecord](#physicalrecord)
    - [PhysicalLocation](#physicallocation)
    - [DigitalRecord](#digitalrecord)
    - [Device](#device)
    - [Endpoint and ArchiveLocation](#endpoint-and-archivelocation)
  - [FHIR Mapping](#fhir-mapping)
  - [Critical semantic distinction: `record_type` vs `medium`](#critical-semantic-distinction-record_type-vs-medium)
  - [Codes, Valuesets, and Dropdowns](#codes-valuesets-and-dropdowns)
  - [Staging vs archival storage](#staging-vs-archival-storage)
  - [Thumbnail policy](#thumbnail-policy)
  - [Record display identifier (`identifier_str`)](#record-display-identifier-identifier_str)
    - [Schema](#schema)
    - [Example](#example)
    - [Usage](#usage)
    - [Critical distinction](#critical-distinction)
  - [API and UI implications](#api-and-ui-implications)

## Core hierarchy

An `Encounter` is the root of two parallel sub-trees:

```
Encounter
├── PhysicalRecord (0..N)         ← physical artifact, no DICOM UIDs
│
└── ImagingStudy (1..1)
      └── Series (1..N)
            └── DigitalRecord (1..N)   ← DICOM instance
                  ├── physical_record FK → PhysicalRecord (null if born-digital)
                  └── ArchiveLocation (0..N)
```

Full path from Collection down to DigitalRecord:

`Collection 1→N Subject 1→N Encounter 1→1 ImagingStudy 1→N Series 1→N DigitalRecord`

- `Collection`: a curated set of subjects whose data was collected under a common scope
  (e.g. a longitudinal twin study or a cleft palate cohort).
- `Subject`: the human or animal whose data is represented.
- `Encounter`: one clinical event or visit.
- `ImagingStudy`: one DICOM study wrapper per encounter.
- `Series`: groups `DigitalRecord`s that share the same modality and acquisition context
  within a study. Different modalities in the same encounter belong to different
  `Series`. `Series` is kept explicit (not collapsed into `ImagingStudy` or
  `DigitalRecord`) because grouping semantics matter for DICOM UID assignment and
  export. **`Series` does not own `record_type`.**
- `PhysicalRecord`: the original physical artifact (acetate film, plaster model, paper
  chart). Lives directly under `Encounter`. Has no DICOM UIDs.
- `DigitalRecord`: one digital instance derived from a `PhysicalRecord` (scan), or a
  born-digital acquisition with no physical counterpart. Corresponds to a DICOM SOP
  Instance.

Example: one encounter contains cephalometric films and scanned study models. This
produces one `ImagingStudy`, two `Series` (modality `RG` and `OSS` respectively), and
one or more `DigitalRecord`s per series. Each `DigitalRecord` links back to its
`PhysicalRecord` (the original film or model), unless it was acquired digitally.

## Models

These rules are strict.

### Subject

Represents a human or animal whose data is held in the archive.

| Field              | Notes                                                                                                |
| ------------------ | ---------------------------------------------------------------------------------------------------- |
| `identifiers`      | M2M → Identifier. Typed, system-scoped references (e.g. Bolton ID, Richardson R-number).             |
| `gender`           | FHIR `Patient.gender` values: `male`, `female`, `other`, `unknown`.                                  |
| `skeletal_pattern` | FK → Coding (null). SNOMED skeletal class code.                                                      |
| `notes`            | Free-text notes from import sources (e.g. "misc" column from Richardson spreadsheet). Null if empty. |

Name, date-of-birth, and other PII fields exist in the model but are **not exposed** via
the API or UI at this time.

### Encounter

The encounter is a model inspired by FHIR Encounter resource, which is defined by the
even that happened when the subject had a physical encounter with the collection
curators/maintainers.

#### Encounter Date

The encounter clearly happened at a specific point in time, and can be recorded in the
`actual_period` fields

- actual_period_start: Encounter start date.
- actual_period_start_raw: Original encounter date token from import sources. Always
  store whatever string we have, especially even if its not complete.
- actual_period_start_precision: Precision of actual_period_start: when the encounter
  date is incomplete or unreadable, then we store here the precision of accuracy.
- actual_period_start_uncertain: True when actual_period_start is inferred from partial
  data
- actual_period_end: Encounter end date. This is unknown and usually not used.

#### Encounter Age

Sometime we don't have the `actual_period`, because the records have been anonymized. In
this case, the `actual_period` is not known and cannot be used. This is why the model
has a `procedure_occurance_age` field. When the actual period is known, this field could
theoretically be useful, and the age could be compute by a function. However, since we
have the field, the field should be computed each time the `actual_period` is set, thus
overwriting any previous setting. It is therefore pseudo-calculated in the sense that
when there is no `actual_period`, it is manually set by the user.

### ImagingStudy

Owns study-level context only:

- `encounter` (OneToOne)
- `collection`
- `study_instance_uid`, external identifiers
- study-level description

Must not own instance-level fields such as file uploads, operator, acquisition datetime,
modality, or `record_type`.

### Series

Groups `DigitalRecord`s within an `ImagingStudy` by shared acquisition context:

- `imaging_study` (FK)
- `modality` (DICOM modality Coding FK)
- `acquisition_location` (FK → Location)
- `series_instance_uid` (optional)
- `description` (optional)

**Does not own `record_type`.** Record type is the responsibility of `PhysicalRecord`
and `DigitalRecord`.

### PhysicalRecord

Represents the original physical artifact produced at an encounter.

| Field                  | Notes                                                                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `encounter`            | FK → Encounter (non-null)                                                                                                                                                       |
| `record_type`          | FK → Coding (non-null). CWRU record type (e.g. `L`, `SM`).                                                                                                                      |
| `sequence_number`      | `PositiveSmallIntegerField` (null until first save). One-based sequence within `(encounter, record_type)`. Auto-assigned on `save()`. Used in `identifier_str` suffix.          |
| `medium`               | Derived `@property` from `record_type`. Not a stored field.                                                                                                                     |
| `acquisition_datetime` | When the original was acquired (X-ray taken, model cast, etc.).                                                                                                                 |
| `operator`             | `CharField`, default `"Unknown"`. The technician who operated the acquisition device. No FK — operator identity is typically not in the system for historical physical records. |
| `device`               | FK → Device (null). Device used to acquire the patient data (e.g. cephalostat).                                                                                                 |
| `locations`            | M2M → PhysicalLocation. Physical archive storage slots where this artifact is held.                                                                                             |
| `identifiers`          | M2M → Identifier. External identifiers.                                                                                                                                         |
| `notes`                | Free-text notes from import sources (e.g. "Errors/Misc." column from Richardson spreadsheet). Null if empty.                                                                    |

**Constraints:**

- `record_type` cannot be null.
- No uniqueness constraint on `(record_type, encounter)`. Multiple physical records of
  the same type may exist per encounter (e.g. multiple photographs taken on the same
  visit).
- `medium` is derived from `record_type` via a model method/property — it is not stored.
  This avoids duplication and sync errors.

### PhysicalLocation

Represents a single physical storage slot (cabinet/shelf/slot) in an archive facility.
Introduced to replace the flat `physical_location_box/shelf/tray/compartment` fields on
`PhysicalRecord` with a structured, reusable model.

| Field     | Notes                                                                               |
| --------- | ----------------------------------------------------------------------------------- |
| `address` | FK → Address (null). Building/facility address.                                     |
| `cabinet` | Cabinet or box number within the facility (e.g. `"1"`, `"10"`).                     |
| `shelf`   | Shelf identifier within the cabinet (e.g. `"A"`, `"B"`).                            |
| `slot`    | Slot or compartment on the shelf (e.g. `"16"`, `"30"`).                             |
| `raw`     | Original unparsed box string from the source spreadsheet. Preserved for provenance. |

A single box string like `1-A-16/17` from the Richardson spreadsheet is parsed into
**two** `PhysicalLocation` rows (cabinet=1, shelf=A, slot=16) and (cabinet=1, shelf=A,
slot=17), both linked to the same `PhysicalRecord` via M2M.

`PhysicalLocation` rows are created with `get_or_create` keyed on
`(cabinet, shelf, slot)`, so the same physical location is shared across records rather
than duplicated.

**Parsing rules (Richardson importer):**

| Input           | Result                                                            |
| --------------- | ----------------------------------------------------------------- |
| `1-A-3`         | one location: (1, A, 3)                                           |
| `1-A-16/17`     | two locations: (1, A, 16) and (1, A, 17)                          |
| `1-A-30/B-1`    | two locations: (1, A, 30) and (1, B, 1)                           |
| `10-9/10`       | two locations with inferred shelf `A`: (10, A, 9) and (10, A, 10) |
| `R Archive Box` | one location with cabinet=full string, shelf='', slot=''          |

### DigitalRecord

Represents one digital instance: either a digitization of a `PhysicalRecord` or a
born-digital acquisition.

| Field                  | Notes                                                                                                                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `physical_record`      | FK → PhysicalRecord (null=True). Null for born-digital records.                                                                                                                               |
| `series`               | FK → Series (non-null). Always required for DICOM grouping.                                                                                                                                   |
| `record_type`          | FK → Coding (non-null). Must equal `physical_record.record_type` when `physical_record` is set; set independently for born-digital.                                                           |
| `sop_instance_uid`     | DICOM SOPInstanceUID. Auto-generated on save.                                                                                                                                                 |
| `acquisition_datetime` | When the physical record was scanned (digitization), or when the data was acquired (born-digital).                                                                                            |
| `operator`             | FK → AUTH_USER_MODEL (null). The system user who performed the scan or born-digital acquisition.                                                                                              |
| `source_file`          | Raw uploaded file (PNG/TIFF/STL). Transient — may be removed after archival.                                                                                                                  |
| `thumbnail`            | Compressed preview image (target 20 KB, hard limit 100 KB JPEG). Persists for browse UX.                                                                                                      |
| `patient_orientation`  | DICOM PatientOrientation (0020,0020), encoded as e.g. `A\F`.                                                                                                                                  |
| `image_transform_ops`  | Ordered JSON list of transform ops applied to the preview image.                                                                                                                              |
| `device`               | FK → Device (null). Device used to digitize the physical record, or to acquire born-digital data.                                                                                             |
| `identifiers`          | M2M → Identifier. External identifiers (e.g. DICOM UIDs from source systems).                                                                                                                 |
| `sequence_number`      | `PositiveSmallIntegerField` (null until first save). One-based sequence within `(encounter, record_type)` among `DigitalRecord`s. Auto-assigned on `save()`. Used in `identifier_str` suffix. |

**Constraints:**

- `series` cannot be null.
- `record_type` cannot be null.
- When `physical_record` is not null: `record_type` must equal
  `physical_record.record_type` (enforced in `clean()`).
- When `physical_record` is not null: `series.imaging_study.encounter` must equal
  `physical_record.encounter` (enforced in `clean()`).

**Paths to Encounter:**

- Via DICOM chain: `digital_record.series.imaging_study.encounter`
- Via physical record (when set): `digital_record.physical_record.encounter`
- Both must resolve to the same `Encounter`.

### Device

Models the physical device used for acquisition or digitization. Modelled after the FHIR
Device resource.

| Field          | Notes                                                            |
| -------------- | ---------------------------------------------------------------- |
| `identifier`   | Device identifier (e.g. serial number or institution asset tag). |
| `display_name` | Human-readable name.                                             |
| `manufacturer` | Manufacturer name.                                               |
| `model_number` | Model number.                                                    |
| `version`      | Firmware/software version string.                                |
| `modalities`   | M2M → Coding. DICOM modality codes this device can produce.      |

### Endpoint and ArchiveLocation

```text
[ArchiveLocation]
    digital_record_id   FK → DigitalRecord
    endpoint_id         FK → Endpoint
    assigned_id         string (DICOM UID, Box file ID, SMB path, etc.)
    status              pending | archived | failed | verified
    archived_at         timestamp

[Endpoint]
    id
    name
    status              active | suspended | off
    connection_type     dicom-stow-rs | dicom-dimse | smb | box | drive | file | other
    address             base URI / address
    config              JSON blob (AE title, port overrides, non-secret settings)
    credentials_encrypted   encrypted secret payload — never exposed via API
```

- `ArchiveLocation` represents one concrete archived copy of a `DigitalRecord` at an
  `Endpoint`.
- `Endpoint` stores the connection definition; `ArchiveLocation` stores the
  record-specific assignment.
- A single `DigitalRecord` may have multiple `ArchiveLocation` rows (one per endpoint it
  has been pushed to).

## FHIR Mapping

| Model             | FHIR resource                                          | Notes                                                                                                                                              |
| ----------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PhysicalRecord`  | No direct equivalent                                   | Closest: `Media` or a custom extension on `ImagingStudy`                                                                                           |
| `DigitalRecord`   | `ImagingStudy` (instance level) or `DocumentReference` | Depends on content type                                                                                                                            |
| `Endpoint`        | `Endpoint`                                             | Nearly 1:1; config blob maps to `header[]` + extensions                                                                                            |
| `ArchiveLocation` | No native resource                                     | Gap — use one `DocumentReference` per row; `content[0].attachment.url` = resolved URL; `relatesTo` chain links copies back to the canonical record |
| `Device`          | `Device`                                               | Nearly 1:1                                                                                                                                         |

## Critical semantic distinction: `record_type` vs `medium`

These are different concepts and must never be substituted.

- **`record_type`** (FK → Coding, ValueSet
  `https://orthodontics.case.edu/fhir/cwru-ortho-record-types`):

  - Owned by both `PhysicalRecord` and `DigitalRecord`.
  - Encodes the clinical study type (e.g. `L` = lateral cephalogram, `SM` = study
    model).
  - Used by humans to identify what kind of record this is. Used to produce correct
    DICOM attributes on export.
  - Cannot be null on either model.

- **`medium`** (derived property on `PhysicalRecord` only):

  - The physical substrate: Acetate Film, Gypsum/Plaster, Paper, etc.
  - Derived from `record_type` via a mapping — not stored as a separate field.
  - Only meaningful for physical artifacts; `DigitalRecord` has no `medium`.

## Codes, Valuesets, and Dropdowns

Clinical codes (record types, modalities, orientations, procedures) are stored as
`Coding` rows and grouped into `ValueSet`s. The UI uses the valueset API
(`/api/valuesets/?type=...`) to populate dropdowns, and the same codes are used when
exporting to open standards (FHIR/DICOM) so integrations stay interoperable.

Valuesets are refreshed from canonical FHIR sources using the generic importer:

```bash
python manage.py import_valuesets --all
```

This is idempotent: it updates existing codes, adds new ones, and removes valueset links
for retired codes so they no longer appear in dropdowns. Update valueset sources in
`bfd9000_web/archive/constants.py` if a terminology endpoint changes or a new valueset
should be managed by the importer.

## Staging vs archival storage

During pre-archive staging inside Django:

- File path layout is intentionally simple and implementation-focused.
- `source_file` is transient and should be removed after archival.

Archival path hierarchy and provider-specific layout belong to the Storage Layer
implementation (see issue #43), including local-storage hierarchy rules.

## Thumbnail policy

Thumbnails are persistent UI previews stored on `DigitalRecord` and follow these
defaults:

- JPEG output
- Max dimensions: 300×300
- Target size: ~20 KB
- Hard size limit: 100 KB
- Default quality: 75 (tunable)

Additional rules:

- Thumbnails are generated at upload only for raster image files (PNG, TIFF, JPEG). No
  thumbnail is generated for 3D file types (STL, PLY, OBJ).
- Upload clients may provide an optional preprocessed preview image
  (`thumbnail_preview`) to be compressed and stored as the thumbnail.
- The thumbnail endpoint serves the persisted thumbnail only; it does not generate
  previews on demand.
- If no thumbnail exists for a `DigitalRecord`, the API and UI return a static fallback
  JPEG image.

For planning: 500k thumbnails at ~20 KB is roughly 10 GB total.

## Record display identifier (`identifier_str` / Bolton record ID)

Each Collection has a specific Subject identifier. The BBGSC has devised, over the
years, a schema to produce a unique identifier for each record, which can be computed
from subject id, encounter age, gender and record type.

`identifier_str` is a computed, read-only field returned by both the `PhysicalRecord`
and `DigitalRecord` API serializers. It is produced by the `bolton_record_id` model
property (defined in `models.py`).

The computed value is **also persisted** as a stored `Identifier` entry on the
`identifiers` M2M field of both `PhysicalRecord` and `DigitalRecord`, using the system
URL:

```
https://orthodontics.case.edu/fhir/identifier-system/bolton-record-id
```

(`SYSTEM_IDENTIFIER_BOLTON_RECORD` in `constants.py`)

This stored identifier is assigned automatically on `save()` and enables database-level
search (e.g. `?search=r011l` on the records API). The `identifier_str` serializer field
continues to return the computed value for UI display and download filenames.

**Lifecycle:**

- On first save (when sequence number is assigned and all required data is present): an
  `Identifier` with `use='official'` is created and attached.
- On subsequent saves where the computed value has changed (e.g. encounter date
  corrected): the old `Identifier` entry is updated to `use='old'` (kept for historical
  reference), and a new `use='official'` entry is created and attached.
- Identifiers with `use='old'` are excluded from search.
- If required data is missing (no subject identifier, no record type), no stored
  identifier is assigned.

### Schema

```
<subject_identifier><record_type_code><sex_code><age><seq>
```

| Component            | Source                                                                                                                                                      | Example  |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `subject_identifier` | Preferred identifier from `Subject.identifiers` (official system first, Bolton system second, first available as fallback)                                  | `B001`   |
| `record_type_code`   | `DigitalRecord.record_type.code`                                                                                                                            | `L`      |
| `sex_code`           | `Subject.gender` mapped: `male→M`, `female→F`, `other→O`, `unknown→U` (FHIR [Patient.gender](https://hl7.org/fhir/patient-definitions.html#Patient.gender)) | `M`      |
| `age`                | Age at encounter formatted as `{years:02d}y{months:02d}m` (zero-padded). Omitted if encounter has no age data.                                              | `08y06m` |
| `seq`                | `DigitalRecord.sequence_number` formatted as `{seq:02d}` (two-digit, zero-padded, one-based). Always present.                                               | `01`     |

### Example

Subject `B001`, lateral cephalogram (`L`), male (`M`), age 8 years 6 months, first
record:

```
B001LM08y06m01
```

No-age variant (encounter has no age data), first record:

```
B001LM01
```

### Usage

- **UI display**: shown in the records list as the human-readable label for each record
  button (fallback to `record.id` if absent).
- **Download filenames**: the download button in `record_detail.html` uses
  `identifier_str` as the base filename (e.g. `B001LM08y06m.png`).
- **API search**: the stored Bolton record ID (`identifiers__value`) enables
  `?search=r011l` on the `/api/records/` and `/api/physical-records/` endpoints.
- **Not for foreign keys**: do not use `identifier_str` as a stable FK or
  external-system integration key. Use the integer PK for that purpose.

### Critical distinction

`identifier_str` (the serializer field) and the stored `identifiers` M2M entries are
related but different:

- The **stored Bolton record ID** (`Identifier` with
  `system=SYSTEM_IDENTIFIER_BOLTON_RECORD`) is a persistent, database-searchable entry,
  auto-assigned on `save()`.
- `identifier_str` (the serializer field) returns the same value computed at
  serialization time — it reads from `bolton_record_id` model property, which recomputes
  live from related fields rather than reading the stored identifier.
- Other `identifiers` entries (DICOM UIDs, subject Bolton IDs, etc.) remain unchanged.

## API and UI implications

- Upload flow creates/reuses `ImagingStudy` and `Series`, then creates a
  `DigitalRecord`.
- If a `PhysicalRecord` for that `record_type` and `Encounter` already exists, link the
  new `DigitalRecord` to it. Otherwise create a new `PhysicalRecord` first.
- For born-digital uploads: create a `DigitalRecord` with `physical_record=None`.
- Subject/Encounter record counts traverse `...imaging_study__series__digital_records`.
- Filtering by encounter/subject traverses the series/study chain.
- UI should present age-at-encounter (with precision/uncertainty) rather than raw
  acquisition dates for clinical views.
