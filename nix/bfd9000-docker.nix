{ dockerTools, pythonEnv, bfd9000-app, coreutils, bash, deps, file, ... }:
dockerTools.buildLayeredImage {
  name = "edu.case.bfd9000";
  tag = "latest";

  contents = [
    pythonEnv
    bfd9000-app
    coreutils
    bash
  ] ++ deps;

  fakeRootCommands = ''
    mkdir -p tmp ./var/tmp
    chmod 1777 tmp ./var/tmp
  '';

  config = {
    # Drop root privileges completely
    User = "1000:1000";

    # Points directly to the initialization wrapper script below
    Cmd = [ "/share/bfd9000_web/entrypoint.sh" ];

    ExposedPorts = {
      "9000/tcp" = {};
    };

    Env = [
      "PYTHONUNBUFFERED=1"
      "LD_LIBRARY_PATH=${file}/lib"
    ];

    WorkingDir = "/share/bfd9000_web";
  };
}
