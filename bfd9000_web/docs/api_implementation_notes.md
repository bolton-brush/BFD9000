# API Implementation Notes

This document describes discrepancies between the API specification
(`api_requirements.md`) and the current backend implementation.

## Subject API

### Identifier semantics

Subjects can have multiple identifiers across different systems. `Identifier.use` is
treated as a **subject-level preference**, not a statement about the issuing system. We
use `official` for the primary, most trusted identifier for the subject in BFD9000, and
`secondary` for cross-reference identifiers from other systems (e.g., Brush). Multiple
`official` identifiers are allowed across systems; display logic should pick the best
identifier using this priority: `official` → `secondary` → `usual` → others.

### Spec vs Implementation

| Spec Field              | Backend Field                               | Notes                                                                                                                                                                                                                             |
| ----------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `identifier` (string)   | `identifiers` (array of Identifier objects) | Backend uses M2M relationship. Prefer `subject_identifier` when present; otherwise pick an identifier by `use` priority (official → secondary → usual → others). To create, must POST identifier separately or extend serializer. |
| `sex` (M/F/O)           | `gender` (male/female/other/unknown)        | Different values. Frontend must map: M->male, F->female, O->other                                                                                                                                                                 |
| `date_of_birth`         | `birth_date`                                | Same format (date), different name                                                                                                                                                                                                |
| `dental_classification` | `skeletal_pattern` (FK to Coding)           | Backend uses Coding reference, not simple string                                                                                                                                                                                  |
| `collection`            | `collection` (SlugRelatedField)             | Compatible - uses short_name                                                                                                                                                                                                      |

### Workarounds for Frontend

1. **Display identifier**: Use `subject.subject_identifier` if present, or select from
   `subject.identifiers` by `use` priority (official → secondary → usual → others), then
   fall back to `subject.id`.
1. **Display subject**: Use `humanname_family, humanname_given` or identifier
1. **Create subject**: Currently requires `gender`, `birth_date`, `humanname_family`,
   `humanname_given` (all required by model)

## Encounter API

### Encounter date precision

Historical imports may include partial or uncertain encounter dates. Encounters still
require a concrete `actual_period_start` for age calculations, so partial dates are
mapped to a **midpoint** of their uncertainty window (e.g., mid-month for month/year,
mid-year for year-only). The original token is preserved in `actual_period_start_raw`,
along with `actual_period_start_precision` (`day|month|year|unknown`) and
`actual_period_start_uncertain` to indicate inferred dates. Dates can be retained
long-term to support historical context or environmental correlation.

### Spec vs Implementation

| Spec Field         | Backend Field         | Notes                                                         |
| ------------------ | --------------------- | ------------------------------------------------------------- |
| `encounter_date`   | `actual_period_start` | Different name                                                |
| `subject_id`       | `subject`             | Backend expects integer PK, not identifier string             |
| `age_at_encounter` | `age_at_encounter`    | Compatible (float, years)                                     |
| -                  | `procedure_code`      | **Required** FK to Coding - not in spec but required by model |

### Workarounds for Frontend

1. **Create encounter**: Must provide `procedure_code` (Coding PK). Need to fetch/create
   a default procedure code.
1. **Filter by subject**: Use `?subject={pk}` not identifier string

## Record API

### Spec vs Implementation

| Spec Field         | Backend Field                 | Notes                                                      |
| ------------------ | ----------------------------- | ---------------------------------------------------------- |
| `encounter_id`     | `encounter`                   | Integer PK                                                 |
| `subject_id`       | N/A                           | Must join through encounter.subject                        |
| `file_size`        | N/A                           | Must get from `imaging_study.source_file` if available     |
| `image_type`       | N/A                           | Must derive from `imaging_study.source_file` extension     |
| `acquisition_date` | `imaging_study.scan_datetime` | Via related imaging study                                  |
| `thumbnail_url`    | `thumbnail.url`               | Backend-qualified storage URI; retrieve through API action |
| `image_url`        | `source_file.url`             | Backend-qualified storage URI; retrieve through API action |

The custom `/api/records/{id}/thumbnail/` and `/api/records/{id}/image/` actions are
authenticated retrieval endpoints. They are deliberately separate from the storage URI
values returned by the serializer.

### Record List Response

The current RecordSerializer doesn't include nested encounter/subject data. To display
subject info in records list, either:

1. Make additional API calls per record
1. Extend RecordSerializer to include nested data (recommended future work)

## Scan / AI Classification Proxy API (BFD9020)

### URL routing structure

The DRF routers live in `archive/api/api.py` (not `archive/urls.py`), mounted at `/api/`
under the `archive:api` namespace. The scan proxy lives in `archive/api/scan/scan.py`,
included under that namespace as `archive:api:scan`, giving URL names such as
`archive:api:scan:get_xray_info`. One exception: `POST /api/scan/tiff-preview/` predates
the proxy, is registered directly in `archive/urls.py` as `archive:scan_tiff_preview`,
and is unrelated to BFD9020.

Templates reverse all of these with `{% url %}` instead of building URL strings in
JavaScript; see "Client-side URL Construction" in `api_requirements.md`.

### Proxy endpoints

Four login-required, POST-only Django views in `archive/api/scan/views.py` forward a
multipart `image` file field to the internal BFD9020 FastAPI service and pass the
classification JSON back to the browser:

| Endpoint                          | URL name                                    | Upstream BFD9020 operation |
| --------------------------------- | ------------------------------------------- | -------------------------- |
| `POST /api/scan/xray-class/`      | `archive:api:scan:classify_xray`            | `POST /xray-class`         |
| `POST /api/scan/lateral-fliprot/` | `archive:api:scan:classify_lateral_fliprot` | `POST /lateral-fliprot`    |
| `POST /api/scan/frontal-fliprot/` | `archive:api:scan:classify_frontal_fliprot` | `POST /frontal-fliprot`    |
| `POST /api/scan/xray-info/`       | `archive:api:scan:get_xray_info`            | `POST /xray-info`          |

Implementation details:

- Calls are made with the auto-generated `bfd9020-ai-api-client` OpenAPI SDK (a
  synchronous `httpx` client with a 30s timeout and SSL verification disabled for the
  internal service). In nix/direnv setups the SDK is symlinked into
  `bfd9000_web/.dummy_deps/bfd9020-ai-api-client` by the flake shell hook; nix-less
  setups must place the built SDK there themselves (see `[tool.uv.sources]` in
  `pyproject.toml`).
- The upstream base URL comes from the `BFD9020_BASE_URL` setting (default
  `http://bfd9020:9020`, the compose-internal hostname; previously the browser-called
  `https://wingate.case.edu/bfd9020`).
- **Success**: upstream `200 OK` JSON is returned to the browser unmodified
  (`prediction`, `probability`, `all_predictions`, `additional_info`).
- **Errors**: missing `image` field → `400`; unreachable backend → `500`; upstream
  non-200 or validation error → upstream status code. Error body shape is
  `{"error": "...", "details": "..."}`.
- Before this change, the browser called the BFD9020 service directly using an
  `ai_base_url` template variable. That variable is gone; the scan page now fetches the
  Django proxy URLs, so the upstream service never needs to be reachable (or
  authenticated) from the client network.

## Recommendations

1. **Short-term**: Frontend adapts to current backend structure
1. **Medium-term**: Add convenience fields to serializers (e.g., `identifier` computed
   field on SubjectSerializer)
1. **Long-term**: Review model to simplify Subject.identifiers to single identifier
   field if multiple identifiers aren't needed
