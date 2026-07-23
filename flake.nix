{
  description = "Django development environment using Nix flakes";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05"; # or unstable
    treefmt-nix.url = "github:numtide/treefmt-nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pybuild.url = "github:pyproject-nix/build-system-pkgs";
    pyproject.url = "github:pyproject-nix/pyproject.nix";
    stl_thumb.url = "github:bolton-brush/STL-Thumb/release";
    # TODO: Change the branch once the necessary PR#11 has been merged
    bfd9020.url = "github:bolton-brush/BFD9020/feature/1-nixify";
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
        hacks = pkgs.callPackage inputs.pyproject.build.hacks { };
        workspace = inputs.uv2nix.lib.workspace.loadWorkspace {
          workspaceRoot = ./bfd9000_web;
        };
        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };
        bfd9020-sdk = inputs.bfd9020.packages.${system}.app.client-sdk;
        bfd9020-sdk-overlay = final: prev: {
          # Adapt the standard Nixpkgs derivation into the uv2nix set!
          bfd9020-ai-api-client = hacks.nixpkgsPrebuilt {
            from = bfd9020-sdk;
            prev = prev.bfd9020-ai-api-client; # preserves dependency linkages in the graph
          };
        };
        pythonBase = pkgs.callPackage inputs.pyproject.build.packages {
          inherit python;
        };
        pythonSet = pythonBase.overrideScope (
          pkgs.lib.composeManyExtensions [
            inputs.pybuild.overlays.wheel
            overlay
            bfd9020-sdk-overlay
          ]
        );
        venv = pythonSet.mkVirtualEnv "venv" workspace.deps.default;
        venvDev = pythonSet.mkVirtualEnv "venvDev" (workspace.deps.all or workspace.deps.default);
        deps = with pkgs; [
          file
          sqlite
          inputs.stl_thumb.packages.${system}.stl-thumb
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
            # Django html formatter
            djlint = {
              enable = true;
              # Includes all .html files by default, but you can override includes if needed:
              includes = [ "*.dj.html" ];
            };
          };
          settings.formatter.shellcheck.excludes = [
            ".envrc"
          ];
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
                inputs.stl_thumb.packages.${system}.stl-thumb
                gnumake
                act
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
              mkdir -p $PROJ_ROOT/.dummy_deps
              ln -sfn ${bfd9020-sdk} $PROJ_ROOT/.dummy_deps/bfd9020-ai-api-client
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
          basedpyright-types = pkgs.stdenvNoCC.mkDerivation {
            name = "basedpyright-types";
            src = ./bfd9000_web;

            nativeBuildInputs = [
              venvDev
              pkgs.basedpyright
            ];

            buildPhase = ''
              echo "Running Basedpyright type checks..."
              ln -sfn ${venvDev} ./.venv
              basedpyright
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
              export LD_LIBRARY_PATH="${pkgs.file}/lib:$LD_LIBRARY_PATH"
              mypy --show-traceback --verbose
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
              python manage.py test --verbosity=2 archive.tests archive.tests.storage
            '';

            installPhase = "mkdir $out";
          };
        };
        apps = {
          load-podman = {
            type = "app";
            program = "${load-podman}/bin/load-podman";
            meta = {
              description = "Load local Podman container images for BFD9000 development";
            };
          };

          dbeaver = {
            type = "app";
            program = "${pkgs.dbeaver-bin}/bin/dbeaver";
            meta = {
              description = "DBeaver SQL Client for database administration";
            };
          };
        };
      }
    );
}
