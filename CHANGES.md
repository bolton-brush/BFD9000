# Changelog

## [0.2.0] - 2026-03-12

- add device information handling in digital record uploads and enforce unique
  constraints on device identifiers
- implement PostgreSQL support with Docker, entrypoint script, and database
  configuration
- restructure digital and physical record models and admin, clarify field ownership,
  align migrations
- implement FHIR ValueSet import functionality and update initialization command

## [0.1.3] - 2026-03-01

- add download button for original image with filename generation

## [0.1.2] - 2026-03-01

- add CSRF_TRUSTED_ORIGINS setting for enhanced security in Django

## [0.1.1] - 2026-03-01

- update API version in SPECTACULAR_SETTINGS to use APP_VERSION
- implement script name handling for subpath hosting and update navigation links to use
  URL template tags
- add script name prefix handling and update STATIC_URL and MEDIA_URL for prefix-aware
  hosting
- update application port from 8000 to 9000 in Docker configuration and documentation

## [0.1.0] - Initial 2026-02-28

- prepend 'v' to app version display in header
- add app version context processor and display in base template
- add GitHub Actions workflow for publishing Docker images to GHCR
- add GitHub Actions workflow for publishing Docker images to GHCR
- replace paginated tables with infinite scroll + total count badge
- complete backend setup (DRF, OpenAPI, Docker/Env)
- implement Docker setup with Dockerfile and docker-compose for backend service
- initialize DRF API with basic CRUD endpoints
