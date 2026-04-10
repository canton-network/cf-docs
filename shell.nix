{ pkgs ? import <nixpkgs> {} }:

let
  pythonBase = pkgs.python311;
  python = pythonBase.withPackages (ps: [
    ps.grpcio-tools
  ]);
  x2mdx = pythonBase.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-d4f3764";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      rev = "d4f3764be8cbe9c48bf672bd36f451cc4a350dac";
    };
    nativeBuildInputs = with pythonBase.pkgs; [
      setuptools
      wheel
    ];
    propagatedBuildInputs = with pythonBase.pkgs; [
      jinja2
      protobuf
      pyyaml
    ];
    doCheck = false;
  };
in
pkgs.mkShell {
  packages = [
    pkgs.gh
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
