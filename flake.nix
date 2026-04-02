{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/25.05";
  };

  outputs = { self, nixpkgs }: let
    supportedSystems = [
      "aarch64-darwin"
      "x86_64-linux"
      "aarch64-linux"
    ];
    forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    pkgs = forAllSystems (system: nixpkgs.legacyPackages.${system});
  in {
    devShells = forAllSystems (system: {
      default = let
        pkgs' = pkgs.${system};
        radlog = pkgs'.writeShellScriptBin "radlog" ''
          exec python -m radlog.cli "$@"
        '';
      in pkgs'.mkShell {
        packages = [
          (pkgs'.python3.withPackages (ps: with ps; [
            requests
            python-dateutil
            pytest
          ]))
          pkgs'.ruff
          pkgs'.basedpyright
          pkgs'.emacs
          radlog
        ];

        shellHook = ''
          export PYTHONDONTWRITEBYTECODE=1
          export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
        '';
      };
    });
  };
}
