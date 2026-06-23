{
  lib,
  rustPlatform,
  ...
}:
rustPlatform.buildRustPackage {
  pname = "stl-thumb";
  version = "0.1.0";

  src = ./..;

  cargoLock = {
    lockFile = ../Cargo.lock;
  };

  meta = with lib; {
    description = "Simple stl to thumbnail generator";
    license = licenses.gpl3Plus;
    platforms = platforms.linux;
    mainProgram = "stl-thumb";
  };
}
