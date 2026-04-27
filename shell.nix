{ pkgs ? import ./nix/nixpkgs.nix }:

let
  pythonBase = pkgs.python311;
  python = pythonBase.withPackages (ps: [
    ps.grpcio-tools
  ]);
  x2mdx = pythonBase.pkgs.buildPythonApplication rec {
    pname = "x2mdx";
    version = "0.1.0+git-f049144";
    pyproject = true;
    src = builtins.fetchGit {
      url = "https://github.com/danielporterda/x2mdx.git";
      ref = "refs/heads/main";
      rev = "f049144b4f13d0bcd25619ea604da383c6aa02d9";
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
