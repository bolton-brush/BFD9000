{
  description = "Django development environment using Nix flakes";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05"; # or unstable
    treefmt-nix.url = "github:numtide/treefmt-nix";
  };

  outputs =
    { ... }@inputs:
    inputs.flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import inputs.nixpkgs { inherit system; };
        pkgs-treefmt = (import inputs.nixpkgs) {
          inherit system;
        };
        python = pkgs.python311;
      in
      {
        formatter =
          let
            treefmtconfig = inputs.treefmt-nix.lib.evalModule pkgs-treefmt {
              projectRootFile = "flake.nix";
              programs = {
                alejandra.enable = true;
                ruff-format.enable = true;
                toml-sort.enable = true;
                yamlfmt.enable = true;
                mdformat.enable = true;
                shellcheck.enable = true;
                shfmt.enable = true;
                nixfmt.enable = true;
              };
              settings.formatter.shellcheck.excludes = [ ".envrc" ];
            };
          in
          treefmtconfig.config.build.wrapper;
        devShells = {
          default = pkgs.mkShell {
            name = "django-env";

            buildInputs =
              with pkgs;
              [
                watchman
                nil
                nixd
                uv
                file
                ruff
                sqlite
              ]
              ++ [
                python
              ];
            shellHook = ''
              export LD_LIBRARY_PATH="${pkgs.file}/lib:$LD_LIBRARY_PATH"
              export UV_PROJECT=$(git rev-parse --show-toplevel)/bfd9000_web
              uv venv
              uv sync --dev
              source bfd9000_web/.venv/bin/activate
            '';
          };
        };
        checks = {
          ruff-lint = pkgs.stdenvNoCC.mkDerivation {
            name = "ruff-lint";
            src = ./.;

            nativeBuildInputs = [ pkgs.ruff ];

            buildPhase = ''
              echo "Running Ruff linter checks..."
              ruff check ./bfd9000_web --exclude bfd9000_web/archive/management,bfd9000_web/archive/tests,bfd9000_web/archive/migrations
            '';

            installPhase = "mkdir $out";
          };
        };
        apps = {
          dbeaver = {
            type = "app";
            program = "${pkgs.dbeaver-bin}/bin/dbeaver";
          };
        };
      }
    );
}
