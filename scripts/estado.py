#!/usr/bin/env python3
"""¿Qué hay hecho y qué está sin hacer?

La cifra que importa no es cuántas muestras hay, sino cuántas tienen lecturas crudas
públicas y ningún genoma ensamblado. Esas se pueden ensamblar hoy, sin laboratorio,
sin permisos y sin pagar secuenciación.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comun import miles, regla  # noqa: E402

AQUI = Path(__file__).parent


def main() -> int:
    origen = AQUI / "results" / "muestras.csv"
    if not origen.exists():
        raise SystemExit("falta results/muestras.csv: corre primero ./limpiar.py")
    with origen.open() as fh:
        muestras = list(csv.DictReader(fh))

    ensambladas = [m for m in muestras if m["ensamblaje"]]
    solo_lecturas = [m for m in muestras if not m["ensamblaje"] and m["corridas"]]
    sin_nada = [m for m in muestras if not m["ensamblaje"] and not m["corridas"]]
    total = len(muestras)

    def pct(n: int) -> str:
        return f"{100 * n / total:.1f} %".replace(".", ",") if total else "—"

    print(regla("="))
    print("ESTADO DEL INVENTARIO".center(51))
    print(regla("="))
    print(f"  {'muestras de patógenos':<30} {miles(total):>9}")
    print(regla())
    print(f"  {'con genoma ensamblado':<30} {miles(len(ensambladas)):>9} {pct(len(ensambladas)):>8}")
    print(f"  {'SOLO LECTURAS, sin ensamblar':<30} {miles(len(solo_lecturas)):>9} {pct(len(solo_lecturas)):>8}")
    print(f"  {'sin secuencia vinculada':<30} {miles(len(sin_nada)):>9} {pct(len(sin_nada)):>8}")
    print(regla("="))
    print("  SIN ENSAMBLAR, POR ESPECIE")
    top = Counter(m["especie"] for m in solo_lecturas if m["especie"]).most_common(6)
    for especie, n in top:
        barra = "█" * max(1, round(24 * n / top[0][1]))
        print(f"  {especie[:26]:<26} {miles(n):>5} {barra}")
    print(regla("="))

    especies = Counter(m["especie"] for m in muestras if m["especie"])
    proyectos = {m["bioproject"] for m in muestras if m["bioproject"]}
    diez = sum(n for _, n in especies.most_common(10))

    resumen = {
        "muestras": total,
        "especies": len(especies),
        "bioprojects": len(proyectos),
        "ensambladas": len(ensambladas),
        "solo_lecturas": len(solo_lecturas),
        "solo_lecturas_pct": round(100 * len(solo_lecturas) / total, 1) if total else 0,
        "sin_secuencia": len(sin_nada),
        "top_sin_ensamblar": top,
        "top_especies": especies.most_common(10),
        "concentracion_top10_pct": round(100 * diez / total, 1) if total else 0,
    }
    (AQUI / "results" / "estado.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
