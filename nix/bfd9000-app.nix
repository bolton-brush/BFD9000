{
  stdenvNoCC,
  pythonEnv,
  file,
  ...
}:
stdenvNoCC.mkDerivation {
  name = "bfd9000-web-prod";
  src = ../bfd9000_web;

  # Pass the production venv into the build environment so we can run collectstatic
  nativeBuildInputs = [ pythonEnv ];

  buildPhase = ''
    echo "Collecting static files..."
    export "LD_LIBRARY_PATH=${file}/lib"
    python manage.py collectstatic --noinput --ignore "input.css"
  '';

  installPhase = ''
    mkdir -p $out/share/bfd9000_web
    cp -r archive BFD9000 manage.py entrypoint.sh staticfiles VERSION $out/share/bfd9000_web
  '';
}
