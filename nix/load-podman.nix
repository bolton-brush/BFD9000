{
  writeShellApplication,
  podman,
  lib,
  ...
}:
writeShellApplication {
  name = "load-podman";

  # 🔗 Nix ensures podman is available in the shell scope at runtime!
  runtimeInputs = [ podman ];

  text = ''
    IMAGE_TAR=$(nix build .#dockerImage --no-link --print-out-paths "$@")
    echo "Found tarball asset at: $IMAGE_TAR"
    podman load -i "$IMAGE_TAR"
    echo "Successfully loaded image into Podman"
  '';

  meta = {
    description = "Utility script to load local podman container images for BFD9000";
    homepage = "https://github.com/open-ortho/edu.case.BFD9000";
    license = lib.licenses.gpl3;
    platforms = lib.platforms.all;
  };
}
