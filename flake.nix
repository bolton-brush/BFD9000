{
  description = "Django development environment using Nix flakes";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05"; # or unstable
    treefmt-nix.url = "github:numtide/treefmt-nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pybuild.url = "github:pyproject-nix/build-system-pkgs";
    pyproject.url = "github:pyproject-nix/pyproject.nix";
  };

  outputs =
    { self, ... }@inputs:
    inputs.flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import inputs.nixpkgs { inherit system; };
        pkgs-treefmt = (import inputs.nixpkgs) {
          inherit system;
        };
        python = pkgs.python313;
        workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./bfd9000_web; };
        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };
        pythonBase = pkgs.callPackage inputs.pyproject.build.packages {
          inherit python;
        };
        pythonSet = pythonBase.overrideScope (
          pkgs.lib.composeManyExtensions [
            inputs.pybuild.overlays.wheel
            overlay
          ]
        );
        venv = pythonSet.mkVirtualEnv "venv" workspace.deps.default;
        venvDev = pythonSet.mkVirtualEnv "venvDev" (workspace.deps.all or workspace.deps.default);
        deps = with pkgs; [
          file
          sqlite
        ];
        bfd9000-app = pkgs.callPackage ./nix/bfd9000-app.nix { pythonEnv = venv; };
        dockerImage = pkgs.callPackage ./nix/bfd9000-docker.nix {
          inherit bfd9000-app deps;
          pythonEnv = venv;
        };
        load-podman = pkgs.callPackage ./nix/load-podman.nix { };
        treefmtconfig = inputs.treefmt-nix.lib.evalModule pkgs-treefmt {
          projectRootFile = "flake.nix";
          programs = {
            alejandra.enable = true;
            toml-sort.enable = true;
            yamlfmt.enable = true;
            mdformat = {
              enable = true;
              plugins = ps: [
                ps.mdformat-gfm
              ];
              settings = {
                wrap = 88;
                end-of-line = "lf";
              };
            };
            shellcheck.enable = true;
            shfmt.enable = true;
            nixfmt.enable = true;
          };
          settings.formatter.shellcheck.excludes = [ ".envrc" ];
        };
      in
      {
        formatter = treefmtconfig.config.build.wrapper;
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
                ruff
                basedpyright
                podman
                podman-compose
                gnumake
              ]
              ++ [
                venvDev
                load-podman
              ]
              ++ deps;

            env = {
              UV_NO_SYNC = "1";
              UV_PYTHON = pythonSet.python.interpreter;
              UV_PYTHON_DOWNLOADS = "never";
            };

            shellHook = ''
              PROJ_ROOT=$(git rev-parse --show-toplevel)/bfd9000_web
              export PYTHONPATH="$PROJ_ROOT:${venvDev}/lib/*/site-packages:$PYTHONPATH"
              export LD_LIBRARY_PATH="${pkgs.file}/lib:$LD_LIBRARY_PATH"
              ln -sfn ${venvDev} $PROJ_ROOT/.venv
            '';
          };
        };
        packages = {
          inherit bfd9000-app dockerImage load-podman;
        };
        checks = {
          inherit dockerImage;
          formatting = treefmtconfig.config.build.check self;
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
          mypy-types = pkgs.stdenvNoCC.mkDerivation {
            name = "mypy-types";
            src = ./bfd9000_web;

            nativeBuildInputs = [ venvDev ];

            buildPhase = ''
              echo "Running Mypy type checks..."
              export PYTHONPATH=$(pwd)
              mypy
            '';

            installPhase = "mkdir $out";
          };
          django-tests = pkgs.stdenvNoCC.mkDerivation {
            name = "django-tests";
            src = ./bfd9000_web;

            nativeBuildInputs = [ venv ] ++ deps;

            buildPhase = ''
              echo "Running Django tests..."
              export PYTHONPATH=$(pwd)
              export LD_LIBRARY_PATH="${pkgs.file}/lib:$LD_LIBRARY_PATH"
              python manage.py test --verbosity=2 archive.tests
            '';

            installPhase = "mkdir $out";
          };
        };
        apps = {
          load-podman = {
            type = "app";
            program = "${load-podman}/bin/load-podman";
          };

          dbeaver = {
            type = "app";
            program = "${pkgs.dbeaver-bin}/bin/dbeaver";
          };
        };
      }
    );
}
