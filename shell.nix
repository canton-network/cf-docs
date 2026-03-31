{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  x2mdx = python.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-1a8a0c4";
    pyproject = true;
    src = pkgs.fetchFromGitHub {
      owner = "danielporterda";
      repo = "x2mdx";
      rev = "1a8a0c44790f7cfaf26407b41c371cc2cbb02a64";
      sha256 = "sha256-GUOx27QBFgZKDIhaPrUfrsNuclDKTSyEy0EQvUM0CDw=";
    };
    nativeBuildInputs = with python.pkgs; [
      setuptools
      wheel
    ];
    propagatedBuildInputs = with python.pkgs; [
      pyyaml
    ];
    doCheck = false;
  };
in
pkgs.mkShell {
  packages = [
    pkgs.nodejs_22
    python
    x2mdx
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
