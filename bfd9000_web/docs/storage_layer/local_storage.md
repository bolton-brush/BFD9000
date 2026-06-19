# Local Storage File Naming Scheme

This schema summarizes how the scanned TIFFs were traditionally stored on local storage
and HDDs. It can be used for a local_storage SL implementation, for reading images
already store there.

## Overview

Archived files are organized hierarchically by collection, subject, and encounter with
structured, meaningful filenames. This ensures files from different collections remain
separate and organized by their data provenance.

See [api_requirements.md](./api_requirements.md) for the complete API specification.

## Directory Structure

```
└── {subject_id}/
    └── {body_part}/
        └── {subject_id}{record_type}{gender}{age}.{ext}
```

## Naming Components

### Directory Hierarchy

- **`{subject_id}`**: Subject ID within that collection
- **`{body_part}`**: Lateral, Frontal, Elbow, etc

### Filename Format

- **`{subject_id}`**: Subject ID within that collection
- **`{record_type}`**: L,F,H, etc
- **`{gender}`**: M,F
- **`{age}`**: `YYyMMy` two digit year with `y` separator two digit month with `m`
  separator.
- **`.{ext}`**: Original file extension (`.png`, `.stl`)
