# Docker Troubleshooting Notes

## Media volume permissions (important)

When the web container runs as a non-root user, Docker named volumes may be owned by
`root` and uploads can fail until ownership is fixed.

Run this one-time command (adjust UID:GID if needed):

```bash
docker run --rm -v bfd9000_media_volume:/data alpine sh -c "chown -R 1000:1000 /data"
```

Notes:

- On Docker Desktop for macOS, named volumes live inside Docker's VM. You generally
  cannot `chown` them directly from the host filesystem.
- Running `chown` via a temporary container (as above) is the expected approach.

## Verify

After fixing ownership, restart the stack and test file upload/thumbnail generation
paths.
