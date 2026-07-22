{
  dockerTools,
  pythonEnv,
  bfd9000-app,
  coreutils,
  bash,
  deps,
  file,
  cacert,
  lib,
  vulkan-loader,
  mesa,
  stdenv,
  ...
}:
dockerTools.buildLayeredImage {
  name = "edu.case.bfd9000";
  tag = "latest";

  contents = [
    pythonEnv
    bfd9000-app
    coreutils
    bash
    cacert
  ]
  ++ deps;

  fakeRootCommands = ''
    mkdir -p tmp ./var/tmp media
    chmod 1777 tmp ./var/tmp media
  '';

  config = {
    # Drop root privileges completely
    User = "1000:1000";

    # Points directly to the initialization wrapper script below
    Cmd = [ "/share/bfd9000_web/entrypoint.sh" ];

    ExposedPorts = {
      "9000/tcp" = { };
    };

    Env = [
      "PYTHONUNBUFFERED=1"
      "LD_LIBRARY_PATH=${
        lib.makeLibraryPath [
          vulkan-loader
          mesa
          file
        ]
      }"
      "SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt"
      "VK_ICD_FILENAMES=${mesa}/share/vulkan/icd.d/lvp_icd.${stdenv.hostPlatform.linuxArch}.json"
    ];

    WorkingDir = "/share/bfd9000_web";
  };
}
