{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.nodejs_23
  ];

  shellHook = ''
    export PATH="$PWD/node_modules/.bin:$PATH"

    if [ -f package.json ] && [ ! -d node_modules ]; then
      echo "Installing npm dependencies..."
      npm install
    fi
  '';
}
