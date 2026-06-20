# Deploy Checklist

- [ ] Decide what the next release version will be
- [ ] Create new release branch with `git flow release start vX.Y.Z`. Make sure the `v`
  prefix is there.
- [ ] Bump `bfd9000_webVERSION` to that version (without the v prefix)
- [ ] Run all tests
- [ ] `make build-test-docker`
- [ ] `make run-test-docker`: open http://localhost:9000/bfd9000 and test the GUI, check
  that the version number is correct, etc.
- [ ] Update the `CHANGES.md` file with all changes between now and last release.
- [ ] `git flow release finish`
- [ ] Once you are back in develop, patch-bump with `-dev` suffix.
- [ ] Trigger docker build and publication on registry by pushing main, develop and
  tags: `git push origin main develop --tags`
