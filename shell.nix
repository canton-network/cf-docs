{ pkgs ? import <nixpkgs> {} }:

let
  pythonBase = pkgs.python311;
  python = pythonBase.withPackages (ps: [
    ps.grpcio-tools
  ]);
  x2mdx = pythonBase.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-4de8e6c";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      rev = "4de8e6ce4bbd9f203839a3722e79d1ab9feb35e0";
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
