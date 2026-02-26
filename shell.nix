{ pkgs ? import <nixpkgs> { } }:

let
  dpmSdkVersion = "3.4.11";
  damlSdkVersion = dpmSdkVersion;
  platform =
    if pkgs.stdenv.hostPlatform.system == "aarch64-darwin" then
      {
        os = "darwin";
        arch = "arm64";
        hash = "sha256-vLwP0O/lpxbGl42bIW6/TS5ZBm9jTujhdCUKNRz2IMQ=";
      }
    else if pkgs.stdenv.hostPlatform.system == "x86_64-linux" then
      {
        os = "linux";
        arch = "amd64";
        hash = "sha256-F3MouNi1eBpu7jf70XKoRF8Y4HtGKSxA/jIgfUzXLM0=";
      }
    else
      throw "Unsupported platform for dpm in shell.nix: ${pkgs.stdenv.hostPlatform.system}";

  dpmSdkTarball = pkgs.fetchurl {
    url = "https://get.digitalasset.com/install/dpm-sdk/dpm-${dpmSdkVersion}-${platform.os}-${platform.arch}.tar.gz";
    hash = platform.hash;
  };

  dpm = pkgs.stdenvNoCC.mkDerivation {
    pname = "dpm";
    version = dpmSdkVersion;
    src = dpmSdkTarball;
    dontConfigure = true;
    dontBuild = true;
    unpackPhase = ''
      tar xzf "$src" --strip-components=1
    '';
    installPhase = ''
      mkdir -p "$out/bin"
      dpm_target="$(readlink bin/dpm)"
      cp "bin/$dpm_target" "$out/bin/dpm"
      chmod +x "$out/bin/dpm"
    '';
  };

  damlPlatform =
    if pkgs.stdenv.hostPlatform.system == "aarch64-darwin" then
      {
        artifact = "macos-x86_64";
        hash = "sha256-48Pn9nffYLKlivqJtaFPBsVSwAt5Fd71cwkTbmyk2+U=";
      }
    else if pkgs.stdenv.hostPlatform.system == "x86_64-darwin" then
      {
        artifact = "macos-x86_64";
        hash = "sha256-48Pn9nffYLKlivqJtaFPBsVSwAt5Fd71cwkTbmyk2+U=";
      }
    else if pkgs.stdenv.hostPlatform.system == "x86_64-linux" then
      {
        artifact = "linux-x86_64";
        hash = "sha256-YHVio6ymJQG7JZWmKOVIZRZyGGCHOE9gy5+umZuhxi0=";
      }
    else if pkgs.stdenv.hostPlatform.system == "aarch64-linux" then
      {
        artifact = "linux-aarch64";
        hash = "sha256-O9CdlwA6oma4XXL6GCXcPqD6gUvodVotPDNWmHkJzDA=";
      }
    else
      throw "Unsupported platform for daml in shell.nix: ${pkgs.stdenv.hostPlatform.system}";

  damlSdkTarball = pkgs.fetchurl {
    url = "https://github.com/digital-asset/daml/releases/download/v${damlSdkVersion}/daml-sdk-${damlSdkVersion}-${damlPlatform.artifact}.tar.gz";
    hash = damlPlatform.hash;
  };

  daml = pkgs.stdenvNoCC.mkDerivation {
    pname = "daml";
    version = damlSdkVersion;
    src = damlSdkTarball;
    dontConfigure = true;
    dontBuild = true;
    unpackPhase = ''
      tar xzf "$src" --strip-components=1
    '';
    installPhase = ''
      mkdir -p "$out/bin" "$out/opt/daml-sdk"
      cp -R . "$out/opt/daml-sdk/"
      ln -s "$out/opt/daml-sdk/daml/daml" "$out/bin/daml"
      chmod +x "$out/opt/daml-sdk/daml/daml"
    '';
  };
in
pkgs.mkShell {
  packages = [
    pkgs.curl
    pkgs.nodejs_22
    pkgs.python3
    dpm
    daml
  ];

  shellHook = ''
    # direnv `use nix` can capture transient nix-shell temp dirs; force stable tmp paths.
    export TMPDIR=/tmp
    export TMP=/tmp
    export TEMP=/tmp
    export TEMPDIR=/tmp

    export PATH="$PWD/node_modules/.bin:$PATH"

    if [ "''${SKIP_NPM_INSTALL:-0}" != "1" ] && [ -f package.json ] && [ ! -d node_modules ]; then
      echo "Installing npm dependencies..."
      if [ -f package-lock.json ]; then
        npm ci
      else
        npm install
      fi
    fi
  '';
}
