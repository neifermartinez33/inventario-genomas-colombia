#!/usr/bin/env python3
"""Junta lo que devolvieron las cuatro bases en una sola tabla.

Cada fuente llega con sus propios nombres de columna; aquí ya vienen todas con las
mismas 18. Esto solo apila: no quita duplicados todavía. Ese es el paso siguiente.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comun import COLUMNAS, ahora, miles, regla  # noqa: E402

AQUI = Path(__file__).parent


def main() -> int:
    filas: list[dict] = []
    por_fuente: dict[str, int] = {}
    archivos = sorted((AQUI / "data").glob("fuente_*.csv"))
    if not archivos:
        raise SystemExit("faltan los archivos de data/: corre primero ./fuentes.py")

    print(regla("="))
    print("UNIFICAR".center(51))
    print(regla("="))
    for archivo in archivos:
        with archivo.open() as fh:
            nuevas = list(csv.DictReader(fh))
        filas.extend(nuevas)
        for f in nuevas:
            por_fuente[f["fuente"]] = por_fuente.get(f["fuente"], 0) + 1

    for nombre, n in sorted(por_fuente.items(), key=lambda kv: -kv[1]):
        print(f"  {nombre[:34]:<34} {miles(n):>14}")
    print(regla())
    print(f"  {'REGISTROS':<34} {miles(len(filas)):>14}")
    taxones = {f['especie'] for f in filas if f['especie']}
    print(f"  {'taxones distintos':<34} {miles(len(taxones)):>14}")
    print(regla("="))

    destino = AQUI / "results" / "registros.csv"
    destino.parent.mkdir(exist_ok=True)
    with destino.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)

    corte = json.loads((AQUI / "results" / "corte.json").read_text())
    corte["unificado"] = {"registros": len(filas), "taxones": len(taxones),
                          "por_fuente": por_fuente, "en": ahora()}
    (AQUI / "results" / "corte.json").write_text(
        json.dumps(corte, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
