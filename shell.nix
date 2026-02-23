{ pkgs ? import <nixpkgs> { } }:

let
  dpmSdkVersion = "3.4.11";
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
in
pkgs.mkShell {
  packages = [
    pkgs.curl
    pkgs.nodejs_22
    pkgs.python3
    dpm
  ];

  shellHook = ''
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
