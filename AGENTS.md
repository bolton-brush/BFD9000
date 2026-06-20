# BFD9000 instructions for developing

Currently, the primary development focus is on the Django server in `bfd9000_web`.

Environment setup is now automatic via `direnv` and `.envrc`. Simply `cd` into the repo
and run `direnv allow` (once): your local `.venv` will be created (if missing),
activated, and Python requirements installed/updated from `bfd9000_web/pyproject.toml`
as needed, from both the dev and main dependency sections. The `pyproject` files are the
**only** source of truth for Python dependencies. Do not add additional python
dependencies to the nix flake `flake.nix`, as it exists only to mirror and package the
UV dependencies to provide a consistent environment whether using the UV packages or the
nix shell by using `uv2nix`. Within the flake, the `venvDev` attribute represents the
python environment for development, including all necessary types and hints for proper
LSP support and CI checks.

The github action uses the nix flake as well, using its respective environment defined
within the flake, `venv`, not `venvDev`. The `nix develop` shell provides the `venvDev`
environment as well as another other non-python packages required by the program, such
as `file` for python-magic and `sqlite` for local development. The `pyproject.toml` is
the source of truth for python dependencies and the `flake.nix` is the source of truth
for any system dependencies. The additional `nix develop` system dependencies are
mirrored exactly into the production build from the `deps` attribute within the flake,
this allows a consistent development experience across development and deployment as all
system dependencies are also locked exactly.

When updating python dependencies, ensure to explicitly run `uv lock` in order to update
the lock file. The nix derivation will automatically use the new dependencies as soon as
the `pyproject.toml` and `uv.lock` are added to git (with `git add`). To manage
dependencies, instead use the `uv add <pkg>` and `uv remove <pkg>`, and
`uv add/remove --dev <pkg>` to add development dependencies, ensure when adding
production dependencies to also add them to development, but do not add development
dependencies to production. Do NOT use `pip` as this will not be tracked and managed by
the build system.

## Reference

- **Main API spec**: [api_requirements.md](./bfd9000_web/docs/api_requirements.md)
- **Data model spec**: [data_model.md](./bfd9000_web/docs/data_model.md)

## Data Model

- Follow the archive hierarchy documented in `bfd9000_web/docs/data_model.md`:
  - `Encounter -> ImagingStudy -> Series -> Record`
- Keep field ownership strict:
  - `record_type` belongs to `Series`
  - upload/acquisition fields belong to `Record`
- Critical warning:
  - `record_type` (SNOMED clinical study type) is **not** the same as `image_type`
    (legacy identifier code like `L`, `SM`)
  - never substitute one for the other in API, filtering, or UI logic

## Typing

- All code should be explicitly typed.
- Prefer direct variable type annotations (for example
  `typed_instance: Record = instance`) over `cast()` whenever possible.
- Use `cast()` only when direct annotations and normal control-flow typing cannot
  express the type clearly.
- Avoid "type-like" protocol/shim objects or other typing-only abstractions that add
  complexity without improving readability.
- The goal of typing is clearer code and fewer errors, not extra boilerplate.
- Zed + basedpyright + ruff is the expected type-checking workflow during development.
- `django-stubs` should be available in the development environment; it is both a
  dev-time and production runtime requirement in order to monkeypatch strong types at
  production time.

For running linters, checkers, and tests, see `Code Cleanliness` within `README.md` in
order to run `ruff`, `mypy`, and `basedpyright`.

Whenever a large change is made, documenting it in `./bfd9000_web/docs` is good
practice.

- Include the collection in the subjects view
- Subject:
  - Name / DoB etc. are unused for now: DO NOT EXPOSE
- Age field needs to be able to handle specific day
  - Just show age in years-month maybe year-month-day? ^^(is month optional?)^^ for now
    yes
- APP FLOW:
  - Subject view -> Encounter view (filter for subject)
    - Add a new subject: subject ID, sex, dental class, etc.
  - Encounters view -> Records view (filter for encounter)
    - Add a new encounter `age_at_encounter`
  - Records view -> Add new record / SCAN
    - Scanning: image comes back, verify details and enter age, click magic AI button ->
      AI Endpoint (9020)
    - AI Endpoint (9020) -> data from AI, fills out the fields in the form, human can
      verify, click submit -> POST new record
    - Docs for the AI endpoint are stored at <https://wingate.case.edu/bfd9020/docs#/>

REFERENCE THE API IN bfd9000_web/docs/api_requirements.md

## Database Compatibility

The local development environment (`python manage.py runserver`) uses **SQLite** by
default. Production and the local docker-compose environment use **PostgreSQL 17**.

To maintain compatibility between dev and production:

- Write all ORM queries, annotations, and aggregations using standard Django ORM
  constructs that work on both backends.
- Do not use PostgreSQL-specific field types (`ArrayField`, `HStoreField`, `JSONField`
  operators like `@>` or `?`, `tsvector`/`tsquery` full-text search, etc.) unless there
  is a strong production benefit.
- Do not write raw SQL that uses PostgreSQL-specific syntax (e.g., `RETURNING`,
  `ON CONFLICT DO UPDATE`, `ILIKE` in raw queries, dollar-quoting).
- If a PostgreSQL-specific feature would be **greatly beneficial** in production (e.g.,
  native full-text search, `JSONB` indexing, `COPY` bulk loads), implement it but:
  1. Document the trade-off clearly in the PR description and in a code comment.
  1. Ensure the feature degrades gracefully or is guarded by a database-engine check so
     that local SQLite development still works.
  1. Flag the incompatibility explicitly to the developer so they can decide.

## Records Identifier

- Records have internal id/pk and identifiers. The user never sees the internal id/pk,
  they always only see the identifier.official (mostly) and the others in the detail
  views.
