{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  x2mdx = python.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-3fbf05a";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      rev = "3fbf05ad1f594d09eddcf46ac3f3209512f4f296";
    };
    nativeBuildInputs = with python.pkgs; [
      setuptools
      wheel
    ];
    propagatedBuildInputs = with python.pkgs; [
      protobuf
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
    export PATH="$HOME/.dpm/bin:$HOME/.daml/bin:$PWD/node_modules/.bin:$PATH"

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
