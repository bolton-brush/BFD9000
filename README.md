# BFD9000

Contrary to popular belief, the BFD9000 stands for Bolton Files Dicomizer 9000. 9000 is
just a huge version number, which is supposed to be intimidating.

Tools and processes to convert the Bolton-Brush Collection to digital format.

## Background

The Bolton Brush Growth Study Collection encompasses various types of X-rays, including
lateral and poster-anterior X-rays of the cranium, as well as X-rays of the hands,
wrists, elbows, knees, chest, pelvis, foot, and ankle, gathered from over 4000 subjects.
This comprehensive collection also consists of dental cast models and paper charts,
serving as a valuable resource for studying human growth and development. The majority
of X-rays were collected in the 1930s, but the collection extended until the 1980s. To
safeguard these valuable assets, approximately 500,000 X-ray films have been scanned and
digitized over time.

Due to the vast scale of this project, numerous researchers, volunteers, and workers
have participated. Consequently, the resulting x-rays were often saved in manually
generated folders, leading to many inconsistencies in formatting and organization. The
aim of this project is to provide tools for:

1. **Cleaning up the existing, scanned data:** This includes orienting all images
   consistently, dividing images that were collected on the same film, and saving them
   in a format intended for medical images (DICOM).
1. **Ensuring that the clean-up will be maintained in the future** with new scans,
   preserving the integrity and usability of the collection.

## Methods

We have chosen to use a neural network for correctly categorizing the images,
determining their correct orientation, and identifying if and how to split them. A
detailed explanation of the algorithms used can be found in the `documentation/` folder
within this repository.

The tools will also likely include a GUI for the operator, assisting them in adding new
scans consistently and avoiding the reintroduction of inconsistencies that were
previously cleaned up.

## Future Uses

Other collections, such as
[the ones in the AAOF Legacy Collection](https://www.aaoflegacycollection.org/), may
also benefit from these tools. If needed, they can utilize them to achieve an
organization based on an open standard like DICOM. This uniform approach could greatly
enhance the research community's access to consistent and standardized datasets.

## Repository Structure

- `bfd9000_web/`: Django application for managing and viewing the BFD9000 data. To run
  the application, follow the instructions in `bfd9000_web/README.md`.

## Code Cleanliness

All python code in this repo should follow the ruff and basedpyright restrictions set
within `ruff.toml` and `pyproject.toml`. Most restrictions apply, primarily for type
safety, code cleanliness, documentation, and maintainability. It is recommended to use
the `ruff` and `basedpyright` LSPs while developing within this repo in order to
maintain these guidelines. Only use `#pyright: ignore[]` or `#noqa: ` comments if
absolutely necessary and never ignore all errors for a line, explicitly list which
errors are being ignored such that in the future if tooling or dependencies improve, we
are able to write more type-safe code. The presence of ANY warnings or errors as a
result of ruff or basedpyright will fail the PR workflow immediately.

Formatters are also used within this entire repo, with those specified in the
`treefmtconfig` attribute within the `flake.nix`. This primarily exists for non-code
files such as markdown, yaml, toml, or sh. To run the formatter, use the `nix fmt`
command at the root of the repo. Failing to pass the format check will fail the github
checks run during a PR merge.

Lastly, for the web component of this repo, `mypy` is additionally run for stronger type
checking on the Django app, as `basedpyright` only does static analysis and cannot
deeply analyse complex Django types. Run `mypy` from the root of the web directory in
order to see any type mismatches or errors. The presence of any warning or error will
immediately fail the PR workflow as well.

## Docker Notes

When you run the app with Docker you will need a one-time volume ownership fix so the
app's non-root user can write media files.

See `docker.md` for the exact commands and troubleshooting steps.

## Django Bootstrap

The archive app provides a convenience management command to initialize a local
development database:

`python bfd9000_web/manage.py initialize`

This runs:

- `migrate`
- `createsuperuser`
- `import_subjects` (Bolton + Lancaster by default)

See full command help:

`python bfd9000_web/manage.py help initialize`

## Manual Login

The application exposes a manual username/password login page present at
`./login/local`, which is not linked to from anywhere by default. This is a maintenance
login to be used for any non-Case ID users or the admin account, which gets created by
running the bootstrap code above. To use, simply manually navigate to this page.

## Generating Security Keys

When rotating keys, generate **two different values**:

- `SECRET_KEY` for Django signing/session security.
- `ENDPOINT_CREDENTIALS_KEY` for endpoint credential encryption (Fernet).

**Do not reuse one key for both variables.**

**Why?** If you use the same value for both `SECRET_KEY` and any encryption key, a leak
in one area (e.g., Fernet credentials) could let an attacker forge Django cookies or
CSRF tokens. Unique, random keys for each cryptographic use greatly reduce risk of
whole-system compromise.

Generate a new Django `SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Generate a new `ENDPOINT_CREDENTIALS_KEY` (valid Fernet key):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set both values in your environment (for example `bfd9000_web/.env` when using
docker-compose).

## Deployment

Deployment is handled by the `bolton-brush/wingate.docker-configs` repository. The Ci
within this repository is only responsible for building and publishing images to GHCR.

______________________________________________________________________

## Configuration: Environment Variables

The web application is configured using the following environment variables. These can
be provided via the environment, a `.env` file, or via Docker Compose.

| Variable Name               | Required?      | Description                                                                        | Example / Default Value                       |
| --------------------------- | -------------- | ---------------------------------------------------------------------------------- | --------------------------------------------- |
| `SECRET_KEY`                | **Yes (prod)** | Django secret key for cryptographic signing.                                       | (must set in production)                      |
| `DEBUG`                     | No             | Enable Django debug mode (do not enable in production).                            | `True` (default), `False`                     |
| `DJANGO_ALLOWED_HOSTS`      | No             | Comma-separated hostnames Django will allow.                                       | `localhost,127.0.0.1`                         |
| `APP_VERSION`               | No             | Set displayed app version; falls back to VERSION file or `nover`.                  | `1.2.0` or blank                              |
| `DJANGO_FORCE_SCRIPT_NAME`  | No             | Subpath hosting prefix (e.g., `/bfd9000`). Needed for reverse proxy support.       | `/bfd9000` or blank                           |
| `CORS_ALLOWED_ORIGINS`      | No             | Comma-separated list of CORS-allowed origins (frontend integration).               | `http://localhost:5173,http://127.0.0.1:5173` |
| `SCANNER_API_BASE`          | No             | Base URL for scanner-side API calls.                                               | `http://localhost:5000`                       |
| `SCANNER_DEVICE_ID`         | No             | Scanner hardware ID string.                                                        | `scanner-001`                                 |
| `BFD9020_BASE_URL`          | No             | Endpoint for the BFD9020 AI microservice (magic AI button).                        | `https://bfd9020:9020`                        |
| `THUMBNAIL_MAX_WIDTH`       | No             | Maximum width for UI/API generated thumbnails (px).                                | `300`                                         |
| `THUMBNAIL_MAX_HEIGHT`      | No             | Maximum height for UI/API generated thumbnails (px).                               | `300`                                         |
| `THUMBNAIL_TARGET_BYTES`    | No             | Target file size for thumbnails, in bytes.                                         | `20480` (20 KB)                               |
| `THUMBNAIL_HARD_MAX_BYTES`  | No             | Hard cap for thumbnail file size, in bytes.                                        | `102400` (100 KB)                             |
| `THUMBNAIL_DEFAULT_QUALITY` | No             | Default thumbnail image quality (0-100).                                           | `75`                                          |
| `THUMBNAIL_MIN_QUALITY`     | No             | Minimum allowed thumbnail quality (0-100).                                         | `40`                                          |
| `CSRF_TRUSTED_ORIGINS`      | No             | Comma-separated list of trusted origins for Django's CSRF check (scheme required). | `https://example.com` or blank                |
| `CAS_ENDPOINT`              | No             | The CAS login page to use for SSO                                                  | `https://login.case.edu/cas/` or blank        |
| `PROXIED_URL`               | No             | The publically redirectable page stub for redirection from CAS (must be https)     | `https://localhost:4430` or blank             |
| `BOX_DEVELOPER_TOKEN`       | No             | A Box developer token for accessing Box.com                                        | blank, must be set in dev if testing Box      |
| `DEBUG_USE_BOX`             | No             | Enable to use Box in dev, otherwise a temporary directory will be made             | `False`, can be set to `True`                 |
| `BOX_JWT_CONFIG_FILE`       | **Yes (prod)** | Path to a Box JWT configuration file for deployment                                | blank, must be set in production              |
| `BOX_FOLDER_ID`             | **Yes (prod)** | The Box root folder ID for all Box storage needed by the application               | blank, must be set in production              |

**For subpath deployments**, you must set `DJANGO_FORCE_SCRIPT_NAME` to your public path
prefix (e.g., `/bfd9000`) to ensure all static/media/API/navigation work behind a proxy
that strips this prefix.

A minimal `.env` example for development:

```env
DEBUG=True
SECRET_KEY=your-generated-key
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=https://your-public-hostname.example.com
DJANGO_FORCE_SCRIPT_NAME=/bfd9000
```

______________________________________________________________________

## Example: Nginx Reverse Proxy with Subpath (SCRIPT_NAME) Hosting

To deploy the Django server under a subpath (e.g., `/bfd9000`), use the following Nginx
configuration:

```nginx
# Redirect /bfd9000 to /bfd9000/ for consistency
location = /bfd9000 {
    return 301 /bfd9000/;
}

# Host Django at /bfd9000/
location /bfd9000/ {
    # Trailing slash strips /bfd9000/ before proxying
    proxy_pass http://bfd9000:9000/;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # Optionally inform upstream of prefix (most Django setups do NOT require this)
    proxy_set_header X-Forwarded-Prefix /bfd9000;
}
```

- Set `DJANGO_FORCE_SCRIPT_NAME=/bfd9000` in the environment so Django generates URLs
  with the correct prefix.
- If your app listens on a different port (e.g., 8000), adjust `proxy_pass` accordingly.
- This config ensures all app URLs, static/media, forms, and fetch endpoints work at
  `/bfd9000`, regardless of the upstream root path.

______________________________________________________________________
