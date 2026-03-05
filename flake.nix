{
  description = "simple hysteria control panel";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};

    env = pkgs.python3.withPackages (ps: with ps; [
      fastapi
      uvicorn
      httpx
      jinja2
      pydantic
      requests
      textual
      typer
      rich
      qrcode
    ]);
  in {
    packages.${system}.default = pkgs.writeShellScriptBin "hystron" ''
      export HYST_DB_PATH="''${HYST_DB_PATH:-/var/lib/hystron/app.db}"
      mkdir -p "$(dirname "$HYST_DB_PATH")"
      exec ${env}/bin/python ${self}/main.py
    '';
  };
}
