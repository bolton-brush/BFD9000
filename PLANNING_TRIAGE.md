# BFD9000 Issue Triage and MVP Planning

**Date:** 2026-02-26\
**Goal:** Deploy MVP in 2 working days (new scans only, historical cleanup deferred)

## MVP Scope

### Core Pipeline

1. **BFD9010 scanner** → acquire 2D radiographs
1. **BFD9000 web app** → operator uploads/manages scans
1. **BFD9020 AI** → automatic classification, orientation, flip detection
1. **DICOM conversion** → Secondary Capture (RG modality) using dicom4ortho templates
1. **Local file storage** → organized folder structure
1. **Box API upload** → archive to Case Western Box folder structure
1. **Database indexing** → ImagingStudy, Subject, Encounter, Record models

### Out of MVP Scope

- Historical archive cleanup (Bolton-Brush TIFF files from drives/Box)
- Advanced AI features (splitting, segmentation)
- CAS single sign-on (use Django auth for now)
- Individual record/subject detail views (list views sufficient)
- Timestamp extraction from legacy TIFFs

______________________________________________________________________

## Issue Triage Results

### ✅ CLOSED (Stale/Superseded)

- **#2** - Step 2: Classification (2023, superseded by #24/RGWizard)
- **#3** - Step 1: Segmentation (2023, research complete)
- **#6** - Develop Labelling Guidelines (2023, no longer relevant)
- **#10** - Evaluation of DL models (2023, superseded by RGWizard)
- **#20** - Prepare bfd9000_dicom (superseded by PR #21)
- **#24** - Add RGWizard AI (COMPLETE - BFD9020 implemented and working)

### 📦 DEFERRED to Historical Project

Moved to: <https://github.com/orgs/open-ortho/projects/3>

- **#15** - Populate DateOfSecondaryCapture from TIFF metadata
- **#16** - Extract patient data from historical filenames
- **#18** - Implement CAS login (use Django auth for MVP)
- **#30** - GitHub Action for GHCR deployment (manual for now)
- **#32** - Frontend scanner/AI integration (verify status in PR #28, may be done)
- **#34** - Individual Records View (partially done in PR #28/#31, detail view deferred)
- **#35** - Individual Subject View (partially done in PR #31, detail view deferred)

### ⚠️ MVP CRITICAL PATH

Should be in: <https://github.com/orgs/open-ortho/projects/1>

| #          | Title                                  | Status                | Notes                                                                       |
| ---------- | -------------------------------------- | --------------------- | --------------------------------------------------------------------------- |
| **PR #28** | DRF API backend                        | In Review             | Has review comments, nearly ready to merge                                  |
| **PR #31** | Django UI                              | Needs Rebase          | Must rebase on #28, integrate with API                                      |
| **PR #21** | bfd9000_dicom DTO refactor             | Decision Needed       | 4mo old, sources missing - merge, salvage, or skip?                         |
| **#14**    | Missing DICOMization capabilities      | Open                  | Need full DICOM metadata (PatientAge, Sex, ID, Orientation, AnatomicRegion) |
| **#19**    | Box API integration                    | Open                  | Have API keys, need to implement upload                                     |
| **#22**    | Docker deployment                      | Mostly Done           | PR #28 has Dockerfile/compose, verify completeness                          |
| **#26**    | Implement DRF                          | Close when #28 merges | Parent issue for PR #28                                                     |
| **#29**    | Restrict records endpoint to read-only | Open                  | Quick win during #28 review                                                 |
| **#33**    | Integrate frontend + backend           | Open                  | Wire #28 API to #31 UI templates                                            |
| **#36**    | Auth on API routes                     | Open                  | Security review of PR #28                                                   |
| **#37**    | Secure BFD9020 API (NEW)               | Open                  | Docker internal networking to isolate AI service                            |

______________________________________________________________________

## Key Repositories

| Repo                 | Purpose                              | Status                            |
| -------------------- | ------------------------------------ | --------------------------------- |
| **edu.case.BFD9000** | Main Django web app + DB models      | Active development (PR #28, #31)  |
| **edu.case.BFD9010** | 2D scanner control/acquisition       | Working (confirmed by user)       |
| **edu.case.BFD9020** | FastAPI AI classification service    | Complete and working              |
| **dicom4ortho**      | DICOM library for orthodontic images | Needs Secondary Capture templates |

______________________________________________________________________

## PRs Needing Attention

### PR #28: Feature/26 implement DRF (2666 additions, 28 deletions)

**Status:** Open since 2025-12-01, last updated 2026-01-28\
**Branch:** feature/26-implement-drf-for-backendfrontend-separation\
**Review Comments:** Multiple unresolved from @zgypa requesting responses

**Implements:**

- Full REST API with DRF ViewSets (Subject, Encounter, Record, ImagingStudy, etc.)
- Nested routing for hierarchical resources
- File upload support (PNG, STL)
- Custom actions: /image/, /thumbnail/, /dicom/ endpoints
- OpenAPI documentation (Swagger/Redoc)
- Docker containerization
- Comprehensive test suite
- Environment-based configuration

**Remaining Work:**

- Address all review comments (zgypa requires "done" or "will not do" on each)
- Resolve human comments (leave for reviewer to close)
- Add tests for ValuesetViewSet to prevent code set cross-contamination
- Verify authentication on all routes (#36)
- Verify read-only restriction on nested records endpoint (#29)

**Decision:** High priority to merge ASAP - foundation for everything else.

______________________________________________________________________

### PR #31: Feature/23 initial django UI (6222 additions, 200 deletions)

**Status:** Open since 2025-12-08, no reviews yet\
**Branch:** feature/23-initial-django-ui-new

**Implements:**

- Django template-based UI with DaisyUI + TailwindCSS
- Authentication (login/logout)
- Paginated table views (subjects, encounters, records)
- Search functionality via PaginatedTableManager JS class
- Form pages for creating subjects and encounters
- Currently uses hardcoded static data

**Remaining Work:**

- Rebase on PR #28 after it merges
- Replace static data with API calls to #28 endpoints
- Complete record_detail.html integration
- Complete subject detail view (beyond list/create)
- Resolve note in PR description: "individual records / subject view are not finished"

**Decision:** Block on #28 merge, then rebase and integrate.

______________________________________________________________________

### PR #21: Add DTO for Django app (4697 additions, 458 deletions)

**Status:** Open since 2025-10-11 (4 months old), no recent activity\
**Branch:** feature/20-bfd9000_dicom-dto

**Implements:**

- Django-style DTO models for DICOM metadata
- Modality-specific converters (TIFF, PNG, JPEG, PDF, STL, radiograph, surface,
  document, photograph)
- Core DICOM builder and compression utilities
- Bolton-Brush metadata extractors
- Comprehensive test suite and documentation

**Problem:**

- `.py` source files missing from working tree (only `.pyc` bytecode remains)
- Likely significant merge conflicts after 4 months
- User mentioned cleaning up dicom4ortho anyway

**Decision Options:**

1. **Abandon** - Use dicom4ortho directly for Secondary Capture conversion
1. **Salvage** - Cherry-pick useful patterns/architecture into new code
1. **Restore & Merge** - Find source files and resolve conflicts

**Recommendation:** Abandon and focus on dicom4ortho integration - cleaner path for
2-day timeline.

______________________________________________________________________

## Next Steps (Manual Planning Required)

### Day 1 Morning (4 hours)

- [ ] Merge PR #28 or decide on fast-track merge strategy
- [ ] Address critical review comments on PR #28
- [ ] Close #26 (parent issue for #28)

### Day 1 Afternoon (4 hours)

- [ ] Rebase PR #31 on merged #28
- [ ] Wire up API calls in templates (replace static data)
- [ ] Test full stack: UI → API → DB

### Day 2 Morning (4 hours)

- [ ] DICOM conversion: integrate dicom4ortho with Secondary Capture templates
- [ ] Implement file naming scheme (see FILE_NAMING_SCHEME.md in PR #28)
- [ ] Test scan → DICOM pipeline

### Day 2 Afternoon (4 hours)

- [ ] Box API integration: implement folder structure upload
- [ ] BFD9010 scanner integration: test upload flow
- [ ] BFD9020 security: Docker internal networking (#37)
- [ ] End-to-end test: scan → classify → DICOM → save → Box → DB

### Parking Lot (Post-MVP)

- CAS login (#18)
- Individual detail views (#34, #35)
- Historical archive processing (entire project #3)
- GitHub Actions for GHCR (#30)

______________________________________________________________________

## Comments Added to Issues

✅ **#32** - Noted that scanner integration may be done in PR #28 (file upload API
exists)\
✅ **#34** - Noted that record detail view partially exists in PR #28/#31\
✅ **#35** - Noted that subject list/create exists, detail view deferred\
✅ **#22** - Noted that Docker files exist in PR #28, verify completeness\
✅ **#24** - Confirmed complete based on BFD9020 working demo, closed\
✅ **#37** - NEW ISSUE created for BFD9020 API security via Docker networking

______________________________________________________________________

## Outstanding Questions for User

1. **PR #21 decision:** Abandon, salvage, or restore/merge the bfd9000_dicom DTO work?
1. **dicom4ortho cleanup:** What specific Secondary Capture templates need to be added?
1. **Box API structure:** What's the desired folder hierarchy in Box?
1. **DICOM metadata:** Which fields should operators enter vs. auto-extract for new
   scans?
1. **PR #28 merge strategy:** Fast-track with known issues or full review resolution
   first?

______________________________________________________________________

## LLM Tool Recommendation

**Use Claude Opus/Sonnet 4 via OpenCode (current session)** - Best for interactive
multi-repo integration work with human steering of key decisions.

**Why not Gemini:** Codebase is ~10k-20k lines total across all repos, fits comfortably
in Claude's context. Quality of reasoning > raw context size for this task.

**Why not Codex async:** Loss of interactive feedback loop. The bottleneck is
integration decisions needing human judgment, not LLM capability.

______________________________________________________________________

## Project Board Organization

**MVP Project (Project #1):** <https://github.com/orgs/open-ortho/projects/1/views/3>

- All issues on Critical Path above
- PRs #28, #31
- Related: edu.case.BFD9020 repo
- Related: dicom4ortho repo

**Historical Cleanup Project (Project #3):**
<https://github.com/orgs/open-ortho/projects/3>

- Issues #15, #16 (data extraction from legacy files)
- All bbc_clean issues (#2, #3, #6, #10)
- Future: bulk DICOM conversion scripts
- Future: deduplication/merge tools
