{ pkgs ? import <nixpkgs> {} }:

let
  pythonEnv = pkgs.python3.withPackages (ps: [
    ps.protobuf
  ]);
in
pkgs.mkShell {
  packages = [
    pkgs.nodejs_22
    pythonEnv
    pkgs.git
  ];

  shellHook = ''
    export PATH="$PWD/node_modules/.bin:$PATH"

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
