{ pkgs ? import ./nix/nixpkgs.nix }:

let
  pythonBase = pkgs.python311;
  python = pythonBase.withPackages (ps: [
    ps.grpcio-tools
    ps.jinja2
    ps.mypy
    ps.protobuf
    ps.pytest
    ps.pyyaml
  ]);
in
pkgs.mkShell {
  packages = [
    pkgs.gh
    pkgs.jdk17_headless
    pkgs.nodejs_22
    pkgs.ruff
    python
  ];

  shellHook = ''
    export PATH="$PWD/node_modules/.bin:$JAVA_HOME/bin:$HOME/.dpm/bin:$HOME/.daml/bin:$PATH"
    export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"

    case " $NODE_OPTIONS " in
      *" --max-old-space-size="*) ;;
      *)
        if [ -z "$NODE_OPTIONS" ]; then
          export NODE_OPTIONS="--max-old-space-size=12288"
        else
          export NODE_OPTIONS="$NODE_OPTIONS --max-old-space-size=12288"
        fi
        ;;
    esac

    if [ -f package.json ] && [ ! -d node_modules ]; then
      echo "Installing npm dependencies..."
      if [ -f package-lock.json ]; then
        npm ci
      else
        npm install
      fi
    fi
  '';
}
