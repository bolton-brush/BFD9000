{
  writeShellApplication,
  podman,
  lib,
  ...
}:
writeShellApplication {
  name = "load-podman";

  runtimeInputs = [ podman ];

  text = ''
    STREAM_SCRIPT=$(nix build .#dockerImage.passthru.stream --no-link --print-out-paths "$@")
    "$STREAM_SCRIPT" | podman load
    echo "Successfully loaded image into Podman"
  '';

  meta = {
    description = "Utility script to load local podman container images for BFD9000";
    homepage = "https://github.com/open-ortho/edu.case.BFD9000";
    license = lib.licenses.gpl3;
    platforms = lib.platforms.all;
  };
}
