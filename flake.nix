{
  description = "ConTeXt Agent - development shell";

  inputs = {
    nixos-config.url = "github:BerndDonner/NixOS-Config";
    nixpkgs.follows = "nixos-config/nixpkgs";
  };

  outputs = { self, nixpkgs, nixos-config, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
        overlays = [
          nixos-config.overlays.unstable
          nixos-config.overlays.pygame-avx2
        ];
      };

      openaiLatest = pkgs.python3Packages.openai.overridePythonAttrs (_old: rec {
        version = "2.47.0";

        src = pkgs.fetchPypi {
          pname = "openai";
          inherit version;
          hash = "sha256-TiBVSKzUME8jW4YgImmRLlW8iCcLFdKgUforU7kDQ6Y=";
        };

        doCheck = false;
        pythonImportsCheck = [ "openai" ];
      });

      pythonDev = import (nixos-config + "/lib/python-develop.nix");
    in
    {
      devShells.${system}.default = pythonDev {
        inherit pkgs;
        inputs = { inherit nixos-config nixpkgs; };
        checkInputs = [ "nixos-config" ];
        secretSets = [ "openai" ];
        flakeLockPath = ./flake.lock;
        symbol = "🐍";
        pythonVersion = pkgs.python3;

        extraPackages = with pkgs; [
          # Laufzeitabhängigkeiten von context-agent
          python3Packages.pyyaml
          python3Packages.pydantic
          openaiLatest

          # Entwicklungswerkzeuge
          python3Packages.pytest
          python3Packages.mypy
          unstable.python3Packages.ruff

          vscode-fhs
        ];

        extraShellHook = ''
          export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          ln -sfn "$(command -v python)" .nix-python
        '';

        message = "🐍 ConTeXt Agent - development shell ready";
      };
    };
}
