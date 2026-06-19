# Deployment + PR 38 Follow-up Plan

## 1) Address PR 38 review comments

- [ ] Review outstanding PR 38 comments (GitHub) and list required fixes
- [ ] Implement fixes + add/adjust tests
- [ ] Re-run relevant test suites
- [ ] Update docs if behavior changes
- [ ] Reply to PR comments with resolution notes

## 2) Mirror BFD9020 GHCR workflow (no registry push in local testing)

- [ ] Add `.github/workflows/publish-ghcr.yml` (tag-triggered publish)
- [ ] Add Docker build-only CI job (PR/push) with no registry push
- [ ] Confirm build context set to `bfd9000_web/`
- [ ] Ensure GHCR workflow mirrors BFD9020 metadata tags/labels

## 3) Local Docker build/test commands

- [ ] Update README with local Docker build/run + compose commands
- [ ] Add Docker build verification command used in CI

## 4) Local verification (no registry push)

- [ ] `docker build -f bfd9000_web/Dockerfile bfd9000_web -t bfd9000-web:test`
- [ ] `docker run --rm -p 9000:9000 bfd9000-web:test`
- [ ] Smoke check `/` (or `/api/schema/` if available)
