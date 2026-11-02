#!/usr/bin/env python3
"""¿De qué parte de Colombia vienen?

El campo de localidad es texto libre: "Colombia: Bogota", "Colombia:Medellin, Antioquia",
o nada. Este paso lo normaliza y mide cuántas muestras dicen de verdad de dónde son.
El hueco que deja es, en sí mismo, un resultado publicable.
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

    total = len(muestras)
    con_depto = [m for m in muestras if m["departamento"]]
    cuenta = Counter(m["departamento"] for m in con_depto)

    print(regla("="))
    print("¿DE QUÉ PARTE DE COLOMBIA?".center(51))
    print(regla("="))
    print(f"  {'muestras':<32} {miles(total):>16}")
    print(f"  {'dicen el departamento':<32} {miles(len(con_depto)):>10} "
          f"{100 * len(con_depto) / total:>4.0f} %")
    print(f"  {'NO lo dicen':<32} {miles(total - len(con_depto)):>10} "
          f"{100 * (total - len(con_depto)) / total:>4.0f} %")
    print(regla())
    mayor = cuenta.most_common(1)[0][1] if cuenta else 1
    for depto, n in cuenta.most_common(8):
        barra = "█" * max(1, round(20 * n / mayor))
        print(f"  {depto[:24]:<24} {miles(n):>6} {barra}")
    if cuenta:
        dos = sum(n for _, n in cuenta.most_common(2))
        print(regla())
        print(f"  los dos primeros concentran {100 * dos / len(con_depto):.0f} %"
              " de las ubicadas")
    print(regla("="))

    # Completitud de los demás metadatos: sin esto, una muestra no sirve para un análisis
    # epidemiológico aunque su genoma esté perfecto.
    def lleno(campo: str) -> int:
        return sum(1 for m in muestras if m.get(campo))

    completitud = {campo: round(100 * lleno(campo) / total, 1)
                   for campo in ("departamento", "anio", "fuente_aislamiento", "huesped")}
    print("  METADATOS COMPLETOS")
    for campo, p in completitud.items():
        barra = "█" * max(1, round(20 * p / 100))
        print(f"  {campo:<24} {str(p).replace('.', ','):>6} % {barra}")
    print(regla("="))

    (AQUI / "results" / "mapa.json").write_text(json.dumps({
        "muestras": total, "con_departamento": len(con_depto),
        "con_departamento_pct": round(100 * len(con_depto) / total, 1),
        "departamentos": cuenta.most_common(),
        "n_departamentos": len(cuenta),
        "completitud_pct": completitud,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
