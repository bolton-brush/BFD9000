{
  description = "stl-thumb: render thumbnails from an stl";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    rust-overlay.url = "github:oxalica/rust-overlay";
    flake-utils.url = "github:numtide/flake-utils";
    appimage.url = "github:ralismark/nix-appimage";
  };

  outputs =
    { ... }@inputs:
    inputs.flake-utils.lib.eachDefaultSystem (
      system:
      let
        overlays = [ (import inputs.rust-overlay) ];
        pkgs = import inputs.nixpkgs { inherit system overlays; };
        rustToolchain = pkgs.rust-bin.stable.latest.default;
        stl-thumb = pkgs.callPackage ./nix/build.nix { };
      in
      {
        packages = {
          inherit stl-thumb;
          appimage = inputs.appimage.bundlers.${system}.default stl-thumb;
          default = stl-thumb;
        };

        devShells.default = pkgs.mkShell {
          buildInputs =
            with pkgs;
            [
              rust-analyzer
              clippy
              rustfmt
              nil
              nixd
              mesa
              vulkan-tools
              vulkan-loader
            ]
            ++ [ rustToolchain ];
          shellHook = ''
            export LD_LIBRARY_PATH="${
              pkgs.lib.makeLibraryPath [
                pkgs.vulkan-loader
                pkgs.mesa
              ]
            }:$LD_LIBRARY_PATH"
            export VK_ICD_FILENAMES="${pkgs.mesa}/share/vulkan/icd.d/lvp_icd.x86_64.json"
          '';
        };
      }
    );
}
