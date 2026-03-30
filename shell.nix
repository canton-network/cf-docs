{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  x2mdx = python.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-206bb4d";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      rev = "206bb4df235ff0c45beecbc6b1a2de07f49c3b86";
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
