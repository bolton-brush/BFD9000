# BFD9000 Django Application

## Prerequisites

There is a nix flake for setting up a developer shell though this is optional. To use
it, install [Nix](https://nixos.org/download.html) and run the following command from
the workspace root:

```bash
nix develop
```

Alternatively, obtain all necessary dependencies listed in the `deps` attribute within
the `flake.nix`, and run `uv venv` from this directory to obtain the python
dependencies. For production testing, use nix as this will maintain a consistent testing
environment across development and deployment.

## Running the Django Application

Do note, SSO will not work on non-https-proxied pages. An easy way to do this is by
using the provided `docker-compose`, see below.

1. Make sure to apply any database migrations and import data into the database:

   ```bash
   cd bfd9000_web
   python manage.py migrate

   # import data into database
   cd docs/collections_data
   python ../../manage.py import_subjects bolton
   python ../../manage.py import_valuesets
   cd ../../

   # or generate synthetic data to test with
   python manage.py generate_synthetic_data
   ```

1. ONLY IF YOU ARE DEVELOPING THE FRONTEND, install DaisyUI and run tailwindcss in a
   seperate terminal window.

   ```bash
   # https://daisyui.com/docs/install/django/
   # Linux / MacOS
   cd bfd9000_web/archive/static/css && curl -sL daisyui.com/fast | bash
   # Windows
   cd bfd9000_web/archive/static/css && powershell -c "irm daisyui.com/fast.ps1 | iex"

   cd ../../../..

   # Linux / MacOS
   bfd9000_web/archive/static/css/tailwindcss -i bfd9000_web/archive/static/css/input.css -o bfd9000_web/archive/static/css/output.css --watch
   # Windows
   bfd9000_web\archive\static\css\tailwindcss.exe -i bfd9000_web/archive/static/css/input.css -o bfd9000_web/archive/static/css/output.css --watch
   ```

1. Start the Django development server:

   ```bash
   # add yourself as a user
   python bfd9000_web/manage.py createsuperuser

   python bfd9000_web/manage.py runserver
   ```

1. Open your web browser and go to `http://127.0.0.1:9000` to view the application.

## Running Tests

```bash
cd bfd9000_web
python manage.py test
```

Run specific test modules:

```bash
python manage.py test archive.tests.test_api_flows
python manage.py test archive.tests.test_valuesets
```

Useful test options:

- `--failfast` - Stop after first failure
- `-v 2` - Verbose output
- `--keepdb` - Keep test database between runs (faster)
- `--parallel` - Run tests in parallel

**Note**: Tests automatically clean up uploaded media files. Test images are stored in a
temporary directory that is deleted after tests complete, so they won't clutter your
`media/uploads/` directory.

## Running additional code checks

The checks outlined within the code cleanliness section of the main `README.md` also
apply here, be sure to check any of those warnings from `mypy`, `ruff`, or
`basedpyright` before completing your PR.

## Local Docker Workflow

Ensure you are within the nix development shell with `nix develop` or with direnv and
`direnv allow`.

Build and load the docker image defined within `flake.nix`:

The `load-podman` utility function is provided for ease of building and loading the
docker. It is defined at `nix/load-podman.nix`

```bash
load-podman
```

This loads the built image into your load podman registry under the name of
`localhost/bfd9000:build`.

Run the container directly (SSO will not work):

```bash
podman run --rm -p 9000:9000 localhost/bfd9000:build
```

Direct access at `http://localhost:9000` does not use the Caddy TLS proxy and is only
intended for development that does not require CAS. Use the compose workflow below when
testing login or any CAS callback behavior.

Or use the provided compose file (Caddy will proxy, allowing SSO to work):

```bash
# Copy the example env file and edit as needed
cd bfd9000_web
cp dot-env.example .env
podman-compose up
```

The HTTPS proxy will be active at `https://localhost:4430`. `CAS_ENDPOINT` identifies
the CAS server, while `PROXIED_URL` must match the externally visible application origin
that CAS uses for service and callback URLs. The values in `dot-env.example` are ready
for the local Caddy workflow; update them when the CAS server or externally visible
application origin differs.

For production, `nix build .#dockerImage` is called directly and uploaded to the OCI
store. You may run this manually to dissect the built docker-image if there is confusion
about where items exist within the docker.

## Import Historical Subjects

Use the unified importer entrypoint for historical datasets:

```bash
python bfd9000_web/manage.py import_subjects bolton --file BoltonSubjects2.xlsx
python bfd9000_web/manage.py import_subjects lancaster --file LancasterDemographic.csv
```

Use `--dry-run` to validate without writing to the database. Use `--include-names` to
populate first/last names when available (default is to leave names null).

If running within a docker container, `podman cp` the files into the container, then
`podman exec` in order to run the correct management commands

## Additional Information

- The application settings can be found in `bfd9000/settings.py`.
- URL routing is defined in `bfd9000/urls.py`.
- For deployment, refer to the WSGI configuration in `bfd9000/wsgi.py`.
