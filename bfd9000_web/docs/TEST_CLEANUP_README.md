# Test Media File Cleanup

## Overview

Tests now automatically clean up uploaded media files using a temporary directory that
gets deleted after tests complete.

## Implementation

### 1. Base Test Classes (`archive/tests/base.py`)

Created two base test classes:

- `CleanupTestCase` - for standard Django tests
- `CleanupAPITestCase` - for REST Framework API tests

Both classes:

- Use `@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)` to redirect media to a temp
  directory
- Implement `tearDownClass()` to clean up the temp directory after all tests complete
- Use `tempfile.mkdtemp()` to create isolated test media storage

### 2. Updated Test Classes

All test classes now inherit from `CleanupAPITestCase`:

- `archive/tests/test_api_flows.py` - `ApiFlowTests`
- `archive/tests/test_subjects.py` - `SubjectTests`
- `archive/tests/test_encounters.py` - `EncounterTests`
- `archive/tests/test_records.py` - `RecordTests`
- `archive/tests/test_valuesets.py` - `ValuesetTests`

## How It Works

1. **Before tests**: A temporary directory is created (e.g.,
   `/tmp/bfd9000_test_media_xxxxx/`)
1. **During tests**: All uploaded files go to this temp directory instead of
   `media/uploads/`
1. **After tests**: `tearDownClass()` removes the entire temp directory and its contents

## Benefits

- **Automatic cleanup** - No manual file deletion needed
- **Isolated** - Test files don't mix with real media files
- **Safe** - Production media files are never touched
- **Clean** - Each test run starts fresh

## Verification

To verify cleanup is working:

```bash
# Before running tests
ls /tmp/bfd9000_test_media_* 2>/dev/null || echo "No temp directories"

# Run tests
python manage.py test archive.tests.test_records

# After tests complete
ls /tmp/bfd9000_test_media_* 2>/dev/null || echo "Cleanup successful - no temp directories remain"
```

## Production Media

The `media/uploads/` directory is only used by:

- The development/production server
- Manual testing with curl/API clients

Test runs will NOT create files in `media/uploads/`.
