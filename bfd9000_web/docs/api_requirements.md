# API Requirements for Frontend

- [API Requirements for Frontend](#api-requirements-for-frontend)
  - [UC01: Add New Records - API Requirements](#uc01-add-new-records---api-requirements)
    - [Complete Workflow for UC01](#complete-workflow-for-uc01)
    - [1. Subject Management](#1-subject-management)
      - [1.1 Search for Subject](#11-search-for-subject)
      - [1.2 Create New Subject](#12-create-new-subject)
      - [1.3 Get Subject Details](#13-get-subject-details)
    - [2. Encounter Management](#2-encounter-management)
      - [2.1 List Encounters for Subject](#21-list-encounters-for-subject)
      - [2.2 Create New Encounter](#22-create-new-encounter)
      - [2.3 Get Encounter Details](#23-get-encounter-details)
      - [2.4 Update Encounter](#24-update-encounter)
      - [2.5 Delete Encounter](#25-delete-encounter)
    - [3. Valuesets](#3-valuesets)
      - [3.1 Get Valueset](#31-get-valueset)
    - [4. Record Management](#4-record-management)
      - [4.1 List Records for Encounter](#41-list-records-for-encounter)
      - [4.2 Search Records (Alternative)](#42-search-records-alternative)
    - [5. Record Creation & Management](#5-record-creation--management)
      - [5.1 Create Record with File Upload](#51-create-record-with-file-upload)
      - [5.2 Get Record Details](#52-get-record-details)
      - [5.3 Update Record Metadata](#53-update-record-metadata)
      - [5.4 Delete Record](#54-delete-record)
    - [6. Image Serving](#6-image-serving)
      - [6.1 Get Record Full Image](#61-get-record-full-image)
      - [6.2 Get Record Thumbnail](#62-get-record-thumbnail)
      - [6.3 Get Record DICOM File](#63-get-record-dicom-file)
    - [7. AI Classification (BFD9020 Proxy)](#7-ai-classification-bfd9020-proxy)
      - [7.1 Classify X-ray Type](#71-classify-x-ray-type)
      - [7.2 Classify Lateral Flip/Rotation](#72-classify-lateral-fliprotation)
      - [7.3 Classify Frontal Flip/Rotation](#73-classify-frontal-fliprotation)
      - [7.4 Get X-ray Info](#74-get-x-ray-info)
  - [UC02: Browse for Records - API Requirements](#uc02-browse-for-records---api-requirements)
    - [Workflow Mapping](#workflow-mapping)
      - [Step 1: Browse/Search Subjects](#step-1-browsesearch-subjects)
      - [Step 2: View Subject Details with Encounters](#step-2-view-subject-details-with-encounters)
      - [Step 3: View Encounter with Records](#step-3-view-encounter-with-records)
      - [Step 4: View Full Record](#step-4-view-full-record)
  - [UC04: Export and Sharing - API Requirements](#uc04-export-and-sharing---api-requirements)
  - [Design Notes and Conventions](#design-notes-and-conventions)
    - [RESTful Resource Hierarchy](#restful-resource-hierarchy)
    - [ID Types](#id-types)
    - [Pagination](#pagination)
    - [Timestamps](#timestamps)
    - [Storage URIs](#storage-uris)
    - [Nested vs. Direct Access](#nested-vs-direct-access)
    - [Status Enumerations](#status-enumerations)
    - [Real-time Updates](#real-time-updates)
    - [Client-side URL Construction](#client-side-url-construction)
  - [Error Handling and HTTP Status Codes](#error-handling-and-http-status-codes)
    - [Standard Status Codes](#standard-status-codes)
    - [Error Response Format](#error-response-format)
    - [Common Error Codes](#common-error-codes)
    - [Validation Rules](#validation-rules)
  - [Summary of Required Endpoints](#summary-of-required-endpoints)
    - [Subject Management](#subject-management)
    - [Encounter Management](#encounter-management)
    - [Valuesets](#valuesets)
    - [Record Management](#record-management)
    - [Image Serving](#image-serving)
    - [AI Classification](#ai-classification)
    - [Total Endpoints: 24](#total-endpoints-24)

Based on the use cases defined in `use_cases.md`, the following API endpoints are
required to support the frontend workflow.

**Note**: UC03 (Record maintenance and administration) will use Django's built-in admin
interface and does not require custom API endpoints.

______________________________________________________________________

## UC01: Add New Records - API Requirements

### Complete Workflow for UC01

1. **Search for subject** → `GET /api/subjects/?search={identifier}`
1. **Create subject if not found** → `POST /api/subjects/`
1. **Create or select encounter** → `POST /api/subjects/{subject_id}/encounters/` or
   select existing
1. **Check for duplicate records** →
   `GET /api/subjects/{subject_id}/records/?age_at_encounter={age}&record_type={type}`
1. **Get form options** → Fetch required valuesets in parallel using type parameter
   (e.g., `GET /api/valuesets/?type=record_types`,
   `GET /api/valuesets/?type=orientations`, etc.)
1. **User scans via localhost** → Browser communicates with BFD9010 bridge on localhost,
   receives PNG or STL file
1. **(Optional) AI-assisted metadata** → Browser sends the scanned image to the BFD9020
   classification proxy (Section 7, e.g. `POST /api/scan/xray-info/`) to pre-fill record
   type, orientation, and flip/rotation fields; operator verifies the suggestions
1. **Upload and create record with metadata** →
   `POST /api/encounters/{encounter_id}/records/` with file upload

### 1. Subject Management

#### 1.1 Search for Subject

**User Action**: Operator searches for subject by identifier

**API Requirement**:

- **Endpoint**: `GET /api/subjects/?search={query}`

- **Query Parameters**:

  - `search`: subject identifier (string)
  - `collection`: optional filter by collection name
  - `page`: pagination page number (default: 1)
  - `page_size`: items per page (default: 20)

- **Response**: Paginated list of matching subjects with fields:

  - `id`, `identifier`, `collection` (subject-level dataset short name), `sex`,
    `date_of_birth` (optional), `dental_classification`, `created_date`
  - `encounter_count`: total number of encounters
  - `record_count`: total number of records

#### 1.2 Create New Subject

**User Action**: Operator creates new subject if not found

**API Requirement**:

- **Endpoint**: `POST /api/subjects/`

- **Request Body** (required fields):

  - `identifier` (string)
  - `collection` (string)
  - `sex` (string, one of: M/F/O)

- **Optional fields**:

  - `date_of_birth` (date)
  - `dental_classification` (string)

- **Response**: Created subject object with generated `id` and all fields

> **Important:** Collections live on the subject. Encounters, imaging studies, and
> records inherit `subject.collection` automatically and therefore no longer expose
> their own `collection` field. Attempting to upload a record for a subject without a
> collection results in a `400 Bad Request` response.

#### 1.3 Get Subject Details

**User Action**: View full subject information with list of encounters

**API Requirement**:

- **Endpoint**: `GET /api/subjects/{id}/`

- **Response**: Complete subject object with:

  - All subject fields
  - `encounters`: array of basic encounter info (id, encounter_date, age_at_encounter,
    record_count)

______________________________________________________________________

### 2. Encounter Management

#### 2.1 List Encounters for Subject

**User Action**: View all encounters for a subject

**API Requirement**:

- **Endpoint**: `GET /api/subjects/{subject_id}/encounters/`

- **Query Parameters**:

  - `page`: pagination page number
  - `page_size`: items per page

- **Response**: Paginated list of encounters with:

  - `id`, `encounter_date`, `age_at_encounter`, `record_count`
  - `modalities`: array of unique modalities present in records (e.g., ["RG", "M3D"])
  - `record_types`: array of unique record types (e.g., ["Lateral", "PA"])

#### 2.2 Create New Encounter

**User Action**: Operator creates encounter (may be implicit when adding first record)

**API Requirement**:

- **Endpoint**: `POST /api/subjects/{subject_id}/encounters/`

- **Request Body**:

  - `encounter_date` (date, required)
  - `age_at_encounter` (float, optional - can be calculated from subject DOB if
    available)

- **Response**: Created encounter object with `id`

#### 2.3 Get Encounter Details

**User Action**: View specific encounter with all records

**API Requirement**:

- **Endpoint**: `GET /api/encounters/{id}/`

- **Response**: Complete encounter object with:

  - `id`, `subject_id`, `encounter_date`, `age_at_encounter`
  - `subject`: basic subject info (id, identifier, collection, sex)
  - `records`: array of record summaries (see Record Management section)

#### 2.4 Update Encounter

**User Action**: Correct encounter date or age

**API Requirement**:

- **Endpoint**: `PATCH /api/encounters/{id}/`
- **Request Body**: Partial update of encounter fields
- **Response**: Updated encounter object

#### 2.5 Delete Encounter

**User Action**: Remove encounter (admin only, cascades to records)

**API Requirement**:

- **Endpoint**: `DELETE /api/encounters/{id}/`
- **Response**: 204 No Content on success

______________________________________________________________________

### 3. Valuesets

**Purpose**: Valuesets provide enumerated options for dropdown fields and validation.
Valuesets are dynamic and can be queried by type.

**Response Format**: All valueset queries return an array of objects with:

- `id` (string): The identifier/code to submit in API requests
- `display` (string): Localized, human-readable text to show in the UI

#### 3.1 Get Valueset

**User Action**: Frontend needs enumeration values for dropdown fields

**API Requirement**:

- **Endpoint**: `GET /api/valuesets/?type={valueset_type}`
- **Query Parameters**:
  - `type` (string, required): The type of valueset to retrieve
- **Response**: Array of objects with `id` and `display` fields

**Supported Valueset Types**:

- **`record_types`**: Available record type options (CWRU Ortho Record Types ValueSet:
  `https://orthodontics.case.edu/fhir/cwru-ortho-record-types`)
- **`orientations`**: Available orientation options
- **`collections`**: Available collection names
- **`sex_options`**: Available sex/gender options
- **`modalities`**: Available modality codes (DICOM codes) with display names

**Example Response Format**:

```json
[
  {"id": "L", "display": "Lateral Cephalogram"},
  {"id": "F", "display": "Frontal Cephalogram"},
  {"id": "H", "display": "Radiograph of Hand & Wrist"}
]
```

**For Modalities**:

```json
[
  {"id": "RG", "display": "Radiography"},
  {"id": "M3D", "display": "3D Model"},
  {"id": "PX", "display": "Photo"}
]
```

**Note**:

- The `id` field contains the code/identifier stored in the database and submitted in
  API requests
- The `display` field contains localized, human-readable text for UI display
- Actual values returned are managed in the database and can be added/modified without
  changing this API specification
- Frontend displays `display` in dropdowns but submits `id` back to the API

**Error Responses**:

- `400 Bad Request` - Missing or invalid `type` parameter
- `404 Not Found` - Unknown valueset type

______________________________________________________________________

### 4. Record Management

#### 4.1 List Records for Encounter

**User Action**: View all records in an encounter or search across subject

**API Requirement**:

- **Endpoint**: `GET /api/encounters/{encounter_id}/records/`

- **Query Parameters**:

  - `record_type`: filter by type
  - `modality`: filter by modality
  - `page`, `page_size`: pagination

- **Response**: Paginated list of records with:

  - `id`, `record_type`, `orientation`, `modality`, `operator`
  - `acquisition_date`, `file_size`, `image_type`
  - `thumbnail_url`: backend-qualified storage URI for the thumbnail
  - `dicom_status`: conversion status
  - `pacs_status`: upload status

#### 4.2 Search Records (Alternative)

**User Action**: Search for records across subject to check for duplicates

**API Requirement**:

- **Endpoint**: `GET /api/subjects/{subject_id}/records/`

- **Query Parameters**:

  - `age_at_encounter`: filter by age (float)
  - `record_type`: filter by type
  - `encounter_date`: filter by date
  - `page`, `page_size`: pagination

- **Response**: Same as 4.1

______________________________________________________________________

### 5. Record Creation & Management

#### 5.1 Create Record with File Upload

**User Action**: Operator uploads scanned file (PNG or STL) and creates record with
metadata

**Note**: Scanning happens directly on localhost via BFD9010 bridge. The frontend
communicates with the bridge, receives the file, and then uploads it to BFD9000.

**API Requirement**:

- **Endpoint**: `POST /api/encounters/{encounter_id}/records/`

- **Content-Type**: `multipart/form-data`

- **Request Body** (form fields):

  - `file` (file upload, required): PNG or STL file from scanner
  - `thumbnail_preview` (file upload, optional): preprocessed preview PNG from UI
    pipeline; used as thumbnail source when provided
  - `record_type` (string, required): value from `/api/valuesets/?type=record_types`
  - `orientation` (string, required): value from `/api/valuesets/?type=orientations`
  - `modality` (string, optional): value from `/api/valuesets/?type=modalities` (if
    omitted, inferred from `record_type`)
  - `operator` (string, optional - defaults to authenticated user)
  - `acquisition_date` (date, optional - defaults to today)
  - `notes` (string, optional)

**Prerequisite**: The encounter’s subject must be assigned to a collection before
uploading. The record and its imaging study automatically inherit that collection; no
collection field is accepted in this payload.

- **Response**: Created record object with:

  - `id` (integer)
  - `encounter_id` (integer)
  - `record_type`, `orientation`, `modality`, `operator`
  - `acquisition_date` (date)
  - `file_size` (integer, bytes)
  - `file_format` (string): "PNG" or "STL"
  - `image_type` (string): e.g., "TIFF", "JPEG2000" (after conversion)
  - `thumbnail_url` (string): backend-qualified storage URI for the thumbnail
  - `image_url` (string): backend-qualified storage URI for the source image
  - `dicom_status` (string): "pending", "processing", "complete", "failed" (for backend
    tracking)
  - `pacs_status` (string): "pending", "uploading", "complete", "failed" (for backend
    tracking)
  - `created_at` (datetime)

**Note**: DICOM conversion and PACS upload happen asynchronously in the background.
Status fields are included for informational purposes but no user action is required.
Failed operations are handled by backend monitoring/alerting systems.

#### 5.2 Get Record Details

**User Action**: View complete record information

**API Requirement**:

- **Endpoint**: `GET /api/records/{id}/`

- **Response**: Complete record object (same fields as 5.1) plus:

  - `encounter`: nested encounter object with subject info
  - `dicom_url` (string, nullable): backend-qualified storage URI for the DICOM file if
    conversion is complete
  - `error_message` (string, nullable): if processing failed

#### 5.3 Update Record Metadata

**User Action**: Operator corrects metadata after record creation

**API Requirement**:

- **Endpoint**: `PATCH /api/records/{id}/`

- **Request Body**: Partial update of editable fields:

  - `record_type`, `orientation`, `modality`
  - `acquisition_date`, `operator`, `notes`

- **Response**: Updated record object

- **Note**: Cannot change `encounter_id` after creation. File cannot be replaced after
  upload.

#### 5.4 Delete Record

**User Action**: Remove record (admin or if DICOM/PACS upload not complete)

**API Requirement**:

- **Endpoint**: `DELETE /api/records/{id}/`
- **Response**: 204 No Content on success
- **Validation**: May prevent deletion if record has been uploaded to PACS

______________________________________________________________________

### 6. Image Serving

**Strategy**: All images are served through authenticated API endpoints to maintain
access control.

#### 6.1 Get Record Full Image

**User Action**: Display full-resolution record image

**API Requirement**:

- **Endpoint**: `GET /api/records/{id}/image/`
- **Response**: Raw source artifact as stored (unmodified passthrough), with source
  `Content-Type` (image/png, image/tiff, image/jpeg, model/stl, etc.)
- **Authentication**: Required
- **Caching**: Support `ETag` and `Last-Modified` headers

#### 6.2 Get Record Thumbnail

**User Action**: Display thumbnail in list views

**API Requirement**:

- **Endpoint**: `GET /api/records/{id}/thumbnail/`
- **Response**: Stored JPEG thumbnail image (max 300x300px, target ~20KB, hard limit
  100KB); returns static fallback if thumbnail does not exist
- **Authentication**: Required
- **Caching**: Support `ETag` and `Last-Modified` headers
- **Note**: Thumbnails are generated only at ingest/upload time for raster images (PNG,
  TIFF, JPEG). For 3D file types (STL, PLY, OBJ), no generated thumbnail is stored;
  endpoint serves static fallback image as `image/jpeg` with HTTP 200.

#### 6.3 Get Record DICOM File

**User Action**: Download DICOM file for external use

**API Requirement**:

- **Endpoint**: `GET /api/records/{id}/dicom/`
- **Response**: DICOM file (.dcm) with `Content-Disposition: attachment`
- **Authentication**: Required
- **Note**: Returns 404 if DICOM conversion not yet complete

### 7. AI Classification (BFD9020 Proxy)

The BFD9020 AI microservice is **not** exposed to the browser directly. BFD9000 proxies
classification requests through Django so the upstream service can stay on the private
internal network and requests inherit the operator's Django session.

**Common requirements for all endpoints in this section**:

- **Method**: `POST` only (other methods return `405 Method Not Allowed`; `OPTIONS`
  returns DRF metadata as usual)
- **Authentication**: Required (Django session login via DRF `SessionAuthentication`;
  anonymous requests receive a JSON `403 Forbidden`, not an HTML login redirect)
- **Request**: `multipart/form-data` with a single required file field named `image`
  (the scanned image as received from the BFD9010 bridge), at most 50MB
- **Success Response** (`200 OK`): the upstream BFD9020 JSON classification result,
  passed through unmodified (e.g. `prediction`, `probability`, `all_predictions`,
  `additional_info`; see the BFD9020 API docs for exact schemas)
- **Error Responses** (all follow the standard
  [Error Response Format](#error-response-format)):
  - `400 Bad Request` (`VALIDATION_ERROR`) - missing `image` file field, or the file
    exceeds the 50MB limit
  - `403 Forbidden` (`PERMISSION_DENIED`) - not logged in
  - `502 Bad Gateway` (`UPSTREAM_UNAVAILABLE`) - the BFD9020 service is unreachable
  - `502 Bad Gateway` (`UPSTREAM_ERROR`) - the BFD9020 service rejected the request
    (e.g. upstream `422`); the upstream status code and body are preserved in
    `error.details`

#### 7.1 Classify X-ray Type

**User Action**: Operator clicks the AI assist button to suggest the record type

**API Requirement**:

- **Endpoint**: `POST /api/scan/xray-class/`
- **Response**: X-ray type classification (e.g. lateral, frontal PA) with confidence
  scores

#### 7.2 Classify Lateral Flip/Rotation

**User Action**: Operator clicks the AI assist button for a lateral film to suggest
correct orientation

**API Requirement**:

- **Endpoint**: `POST /api/scan/lateral-fliprot/`
- **Response**: Predicted `flip` (bool) and `rotation` angle with confidence scores

#### 7.3 Classify Frontal Flip/Rotation

**User Action**: Operator clicks the AI assist button for a frontal film to suggest
correct orientation

**API Requirement**:

- **Endpoint**: `POST /api/scan/frontal-fliprot/`
- **Response**: Predicted `flip` (bool) and `rotation` angle with confidence scores

#### 7.4 Get X-ray Info

**User Action**: Operator clicks the AI assist button to extract general image metadata

**API Requirement**:

- **Endpoint**: `POST /api/scan/xray-info/`
- **Response**: General X-ray information extracted by the BFD9020 service

**Note**: `POST /api/scan/tiff-preview/` is a separate endpoint that converts a scanned
TIFF into a browser-previewable image. It predates the classification proxy and is not
part of the BFD9020 integration.

______________________________________________________________________

## UC02: Browse for Records - API Requirements

**Note**: Browse endpoints are covered in sections 1-4 above. This section provides the
complete workflow mapping.

### Workflow Mapping

#### Step 1: Browse/Search Subjects

- **Use**: `GET /api/subjects/` (Section 1.1)
- Returns subjects with encounter_count, record_count, dental_classification

#### Step 2: View Subject Details with Encounters

- **Use**: `GET /api/subjects/{id}/` (Section 1.3)
- Returns subject with list of encounters including modalities and record counts

#### Step 3: View Encounter with Records

- **Use**: `GET /api/encounters/{id}/` (Section 2.3)
- Returns encounter with full list of records including thumbnails

#### Step 4: View Full Record

- **Use**: `GET /api/records/{id}/` (Section 5.2)
- **Use**: `GET /api/records/{id}/image/` (Section 6.1) to display image
- Returns complete record metadata and serves full-resolution image

______________________________________________________________________

## UC04: Export and Sharing - API Requirements

**Status**: Not yet implemented.

Future API endpoints will include:

- Bulk export of records in DICOM format
- Sharing records with external users/systems
- Generate export packages with metadata
- Query interface for DICOM nodes

Potential endpoints:

- `POST /api/exports/` - Create export job
- `GET /api/exports/{id}/` - Check export status
- `GET /api/exports/{id}/download/` - Download completed export package

______________________________________________________________________

## Design Notes and Conventions

### RESTful Resource Hierarchy

The API follows a clear resource hierarchy:

```
/api/subjects/{id}/
  ├── /encounters/
  │     └── /{id}/
  │           └── /records/
  │                 └── /{id}/
  └── /records/ (search across all encounters)
```

### ID Types

- All resource IDs are **integers** except where noted
- Consistent ID types simplify frontend type systems

### Pagination

- All list endpoints support pagination
- Query parameters: `page` (1-indexed), `page_size` (default: 20, max: 100)
- Response includes: `count`, `next`, `previous`, `results`

### Timestamps

- All timestamps in ISO 8601 format with timezone: `2025-11-29T14:30:00Z`
- Date-only fields in ISO 8601 date format: `2025-11-29`

### Storage URIs

Despite their `_url` suffix, `image_url`, `thumbnail_url`, and `dicom_url` contain
backend-qualified storage URIs, not HTTP URLs. Their format is
`<backend-scheme>://<backend-locator>`:

- The scheme selects a backend registered with the server's `URIStorageBackend`.
- The remainder is an opaque path or file handle interpreted by that backend.
- For example, `box://123456789` selects the Box backend and identifies Box file
  `123456789`.

API clients must treat these values as opaque storage metadata. They must not prepend
the API base URL, attempt to dereference the URI, or use it to access the storage
provider directly. To retrieve content, clients use the separate authenticated
`/api/records/{id}/image/`, `/api/records/{id}/thumbnail/`, and
`/api/records/{id}/dicom/` endpoints. The server resolves the stored URI internally.
Keeping storage location separate from the download endpoints allows the configured
backend to change without changing the client-facing retrieval API.

### Nested vs. Direct Access

- Resources can be accessed both through parent hierarchy and directly:

  - Nested: `POST /api/encounters/{id}/records/` (creates record in specific encounter)
  - Direct: `GET /api/records/{id}/` (access any record directly)

- This pattern balances REST semantics with practical access needs

### Status Enumerations

Standardized status values:

**Scan Status**: `initiated`, `scanning`, `complete`, `failed`

**DICOM Status**: `pending`, `processing`, `complete`, `failed`

**PACS Status**: `pending`, `uploading`, `complete`, `failed`

### Real-time Updates

For long-running operations (scans, DICOM conversion), clients can:

1. **Poll** the resource endpoint (simple, recommended for MVP)
1. **WebSocket** (future): Connect to `ws://server/api/{resource}/{id}/stream/`

Polling recommended interval: 1-2 seconds during active operations

### Client-side URL Construction

Frontend code served by Django **must not** hard-code or hand-assemble API URLs in
JavaScript (e.g. `'/api/records/'`, `` `${BASE_URL}/xray-info` ``). URLs must be
reversed server-side with the Django `{% url %}` template tag and injected into the
script:

```html
<script>
  const response = await fetch("{% url 'archive:api:digitalrecord-list' %}");
</script>
```

For parameterized routes, reverse the URL with a placeholder PK and substitute the real
value in JavaScript:

```html
<script>
  const url = "{% url 'archive:api:encounter-detail' pk='0' %}".replace('0', encounterId);
</script>
```

This keeps URL generation in one place (Django's URLconf), so endpoint moves, namespace
changes, and subpath deployments (`DJANGO_FORCE_SCRIPT_NAME`) do not silently break
client-side requests.

______________________________________________________________________

## Error Handling and HTTP Status Codes

### Standard Status Codes

**Success**:

- `200 OK` - Successful GET, PATCH
- `201 Created` - Successful POST, includes `Location` header
- `204 No Content` - Successful DELETE

**Client Errors**:

- `400 Bad Request` - Invalid request body or parameters
- `401 Unauthorized` - Not authenticated (redirect to CAS login)
- `403 Forbidden` - Authenticated but not authorized for this resource
- `404 Not Found` - Resource doesn't exist
- `409 Conflict` - Resource conflict (e.g., duplicate record)
- `422 Unprocessable Entity` - Validation error

**Server Errors**:

- `500 Internal Server Error` - Unexpected server error
- `503 Service Unavailable` - External service (e.g., PACS) unavailable

### Error Response Format

All error responses follow this structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid record metadata",
    "details": {
      "record_type": ["This field is required"],
      "orientation": ["Must be one of: left, right"]
    }
  }
}
```

### Common Error Codes

- `AUTHENTICATION_REQUIRED` - 401
- `PERMISSION_DENIED` - 403
- `NOT_FOUND` - 404
- `VALIDATION_ERROR` - 422
- `DUPLICATE_RECORD` - 409
- `FILE_TOO_LARGE` - 413
- `UNSUPPORTED_FILE_TYPE` - 415
- `UPSTREAM_UNAVAILABLE` - 502 (BFD9020 proxy: backend unreachable)
- `UPSTREAM_ERROR` - 502 (BFD9020 proxy: backend rejected the request; see
  `error.details.upstream_status`)
- `PROCESSING_FAILED` - 500

### Validation Rules

**Subject Creation**:

- `identifier` must be unique within collection
- `sex` must be a valid value from `/api/valuesets/?type=sex_options`
- `collection` must be a valid value from `/api/valuesets/?type=collections`

**Encounter Creation**:

- `encounter_date` cannot be in the future
- If `age_at_encounter` not provided and subject has `date_of_birth`, calculate
  automatically
- Cannot create encounter with date before subject's `date_of_birth`

**Record Creation**:

- `file` must be provided and must be PNG or STL format
- Maximum file size: 100MB (configurable)
- `record_type` must be a valid value from `/api/valuesets/?type=record_types`
- `orientation` must be a valid value from `/api/valuesets/?type=orientations`
- `modality` must be a valid value from `/api/valuesets/?type=modalities` when provided;
  otherwise it is inferred from `record_type`
- Encounter subject must already belong to a valid collection; uploads are rejected
  otherwise
- `acquisition_date` cannot be in the future
- File content must match file extension (validated via magic bytes)

______________________________________________________________________

## Summary of Required Endpoints

### Subject Management

| Method | Endpoint              | Purpose                                 |
| ------ | --------------------- | --------------------------------------- |
| GET    | `/api/subjects/`      | Search/browse subjects with pagination  |
| POST   | `/api/subjects/`      | Create new subject                      |
| GET    | `/api/subjects/{id}/` | Get subject details with encounter list |

### Encounter Management

| Method | Endpoint                                 | Purpose                     |
| ------ | ---------------------------------------- | --------------------------- |
| GET    | `/api/subjects/{subject_id}/encounters/` | List encounters for subject |
| POST   | `/api/subjects/{subject_id}/encounters/` | Create new encounter        |
| GET    | `/api/encounters/{id}/`                  | Get encounter with records  |
| PATCH  | `/api/encounters/{id}/`                  | Update encounter metadata   |
| DELETE | `/api/encounters/{id}/`                  | Delete encounter (admin)    |

### Valuesets

| Method | Endpoint          | Purpose                                |
| ------ | ----------------- | -------------------------------------- |
| GET    | `/api/valuesets/` | Get valueset by type (query parameter) |

### Record Management

| Method | Endpoint                                  | Purpose                       |
| ------ | ----------------------------------------- | ----------------------------- |
| GET    | `/api/encounters/{encounter_id}/records/` | List records in encounter     |
| GET    | `/api/subjects/{subject_id}/records/`     | Search records across subject |
| POST   | `/api/encounters/{encounter_id}/records/` | Create record from scan       |
| GET    | `/api/records/{id}/`                      | Get complete record details   |
| PATCH  | `/api/records/{id}/`                      | Update record metadata        |
| DELETE | `/api/records/{id}/`                      | Delete record                 |

### Image Serving

| Method | Endpoint                       | Purpose                     |
| ------ | ------------------------------ | --------------------------- |
| GET    | `/api/records/{id}/image/`     | Serve full-resolution image |
| GET    | `/api/records/{id}/thumbnail/` | Serve thumbnail image       |
| GET    | `/api/records/{id}/dicom/`     | Download DICOM file         |

### AI Classification

| Method | Endpoint                     | Purpose                           |
| ------ | ---------------------------- | --------------------------------- |
| POST   | `/api/scan/xray-class/`      | Classify X-ray type               |
| POST   | `/api/scan/lateral-fliprot/` | Suggest flip/rotation (lateral)   |
| POST   | `/api/scan/frontal-fliprot/` | Suggest flip/rotation (frontal)   |
| POST   | `/api/scan/xray-info/`       | Extract general X-ray information |

### Total Endpoints: 24

All endpoints support proper REST semantics with appropriate HTTP verbs and status
codes.

**Note**: Scanner integration is handled entirely on localhost via BFD9010 bridge. The
frontend communicates directly with the bridge, and BFD9000 only receives the resulting
PNG or STL file via the record creation endpoint. AI classification is the inverse: the
BFD9020 service is internal-only, so the browser calls the Django proxy endpoints in
Section 7 rather than talking to BFD9020 directly.
