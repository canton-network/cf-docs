{ pkgs ? import <nixpkgs> {} }:

let
  pythonBase = pkgs.python311;
  python = pythonBase.withPackages (ps: [
    ps.grpcio-tools
  ]);
  x2mdx = pythonBase.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-69af738";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      ref = "refs/heads/main";
      rev = "69af73808c2fbaa3d101a53f98263d502dd49560";
      allRefs = true;
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
