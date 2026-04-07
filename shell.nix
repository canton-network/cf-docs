{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  x2mdx = python.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-5f910e1";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      rev = "5f910e1e85946e4b49a0f591f63905957151bf90";
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
