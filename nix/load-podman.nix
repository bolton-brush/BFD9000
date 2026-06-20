{
  writeShellApplication,
  podman,
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
}
