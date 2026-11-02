#!/usr/bin/env python3
"""Deja una fila por muestra y se queda solo con los patógenos.

Tres cosas pasan aquí, y las tres cambian el número:

1. **Una muestra, una fila.** La misma muestra puede estar en varias bases. La clave es
   el BioSample; si falta, el ensamblaje; si falta, la primera corrida.
2. **Una muestra, una especie.** Las bases no están igual de al día: BV-BRC todavía llama
   *Enterobacter cloacae* a lo que NCBI ya reclasificó como *E. hormaechei*. Se toma la
   especie de la fuente con la taxonomía más reciente.
3. **Patógeno o no.** Pedir «bacterias aisladas en Colombia» devuelve bacterias, no
   patógenos: entra *Candidatus Methylomirabilis* sacada de suelo. Se queda lo que NCBI
   Pathogen Detection vigila, más los géneros clínicos de la lista de abajo.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from comun import (COLUMNAS, ahora, departamento, especie_estandar, limpio, miles,  # noqa: E402
                   muestra_id, regla)

AQUI = Path(__file__).parent

# La fuente con la taxonomía más al día manda sobre las demás.
PRIORIDAD = {"NCBI Pathogen Detection": 0, "ENA": 1, "NCBI Assembly": 2,
             "NCBI BioSample": 3, "BV-BRC": 4}

# Géneros clínicos que Pathogen Detection no vigila como grupo propio pero que sí son
# patógenos humanos. Las levaduras y los hongos dimórficos están aquí.
GENEROS_CLINICOS = {
    "Candida", "Cryptococcus", "Aspergillus", "Fusarium", "Histoplasma",
    "Paracoccidioides", "Coccidioides", "Sporothrix", "Talaromyces", "Blastomyces",
    "Trichosporon", "Rhodotorula", "Malassezia", "Scedosporium", "Lomentospora",
    "Mycobacterium", "Mycobacteroides", "Mycolicibacterium", "Nocardia",
    "Brucella", "Bordetella", "Legionella", "Leptospira", "Borrelia", "Treponema",
    "Rickettsia", "Orientia", "Bartonella", "Coxiella", "Francisella", "Yersinia",
    "Shigella", "Neisseria", "Moraxella", "Stenotrophomonas", "Achromobacter",
    "Elizabethkingia", "Chryseobacterium", "Ralstonia", "Pandoraea", "Cupriavidus",
    "Mammaliicoccus", "Gemella", "Abiotrophia", "Granulicatella", "Kingella",
    "Aggregatibacter", "Capnocytophaga", "Fusobacterium", "Prevotella",
    "Porphyromonas", "Actinomyces", "Cutibacterium", "Bacteroides", "Parabacteroides",
    "Peptostreptococcus", "Veillonella", "Helicobacter", "Arcobacter",
}

# Ambientales o claramente no patógenas que, pese a lo anterior, no deben entrar.
# Se revisaron una por una; el motivo está al lado.
EXCLUIR = {
    "Candidatus methylomirabilis": "bacteria de suelo, oxidante de metano",
    "Vibrio natriegens": "marina, no patógena; se usa como chasis de laboratorio",
    "Listeria kieliensis": "ambiental, no patógena para humanos",
    "Listeria welshimeri": "ambiental, no patógena",
    "Listeria innocua": "ambiental, no patógena (el nombre lo dice)",
    "Listeria seeligeri": "ambiental, rara vez patógena",
    "Listeria grayi": "ambiental",
    "Bacillus subtilis": "ambiental, usada en industria",
    "Escherichia albertii": "se evalúa aparte; se conserva por ser enteropatógena",
}
EXCLUIR.pop("Escherichia albertii")     # sí entra: es enteropatógena reconocida

# Oportunistas que la regla automática deja fuera pero que sí causan infección humana.
INCLUIR = {
    "Mycolicibacterium fortuitum", "Clostridium tertium", "Mammaliicoccus sciuri",
    "Pandoraea pnomenusa", "Cupriavidus pauculus", "Achromobacter xylosoxidans",
}

PLANTAS = re.compile(
    r"^(Xanthomonas|Ralstonia solanacearum|Pseudomonas syringae|Erwinia|Dickeya|"
    r"Pectobacterium|Clavibacter|Xylella|Candidatus Liberibacter|Phytophthora|"
    r"Moniliophthora|Fusarium oxysporum|Hemileia|Macrophomina|Pseudocercospora|"
    r"Mycosphaerella|Colletotrichum|Ceratocystis|Sclerotinia|Botrytis|Rhizoctonia|"
    r"Puccinia|Ustilago|Magnaporthe|Pyricularia|Verticillium|"
    r"Burkholderia (gladioli|glumae|plantarii))", re.IGNORECASE)

# `Bacillus` es un grupo de Pathogen Detection por el complejo B. cereus, pero el género
# está lleno de especies industriales y de suelo. Solo entran las del complejo patógeno.
BACILLUS_PATOGENOS = {
    "Bacillus cereus", "Bacillus anthracis", "Bacillus thuringiensis",
    "Bacillus mycoides", "Bacillus toyonensis", "Bacillus wiedmannii",
    "Bacillus paranthracis", "Bacillus cytotoxicus", "Bacillus pseudomycoides",
    "Bacillus albus", "Bacillus pacificus", "Bacillus tropicus",
}

FTP = "https://ftp.ncbi.nlm.nih.gov/pathogen/Results/"
CACHE_GRUPOS = AQUI / "data" / "grupos_pathogen_detection.txt"


def vigilados() -> tuple[set[str], set[str]]:
    """Qué vigila NCBI Pathogen Detection, leído de los nombres de sus carpetas.

    Así la lista se actualiza sola cuando NCBI añade un grupo, en vez de quedarse
    escrita a mano en este archivo.
    """
    if CACHE_GRUPOS.exists():
        nombres = CACHE_GRUPOS.read_text().split()
    else:
        texto = requests.get(FTP, timeout=120).text
        nombres = sorted({g for g in re.findall(r'href="([A-Za-z_]+)/"', texto)
                          if g != "BioProject_Hierarchy"})
        CACHE_GRUPOS.write_text("\n".join(nombres))
    generos, especies = set(), set()
    for nombre in nombres:
        partes = nombre.split("_")
        generos.add(partes[0].capitalize())
        if len(partes) >= 2 and partes[1].islower():
            especies.add(especie_estandar(f"{partes[0]} {partes[1]}"))
        # "Escherichia_coli_Shigella" nombra dos géneros en una carpeta
        for p in partes[1:]:
            if p[:1].isupper():
                generos.add(p.capitalize())
    return generos, especies


def es_patogeno(especie: str, generos: set[str], especies: set[str]) -> bool:
    if not especie or especie in EXCLUIR:
        return False
    # Identificada solo hasta género ("Nocardia", "Enterobacter"): no se puede afirmar que
    # sea patógena ni usarla en un análisis por especie. Queda fuera, pero queda listada.
    if " " not in especie:
        return False
    if especie in INCLUIR or especie in especies:
        return True
    genero = especie.split()[0]
    if genero == "Bacillus":
        return especie in BACILLUS_PATOGENOS
    return genero in generos or genero in GENEROS_CLINICOS


def main() -> int:
    origen = AQUI / "results" / "registros.csv"
    if not origen.exists():
        raise SystemExit("falta results/registros.csv: corre primero ./unificar.py")
    with origen.open() as fh:
        registros = list(csv.DictReader(fh))

    print(regla("="))
    print("LIMPIAR".center(51))
    print(regla("="))
    print(f"  registros de entrada{miles(len(registros)):>31}")

    # --- 1. agrupar por muestra ---------------------------------------------
    por_muestra: dict[str, list[dict]] = defaultdict(list)
    for r in registros:
        por_muestra[muestra_id(r)].append(r)
    print(f"  muestras distintas{miles(len(por_muestra)):>33}")
    print(f"  registros que eran la misma muestra"
          f"{miles(len(registros) - len(por_muestra)):>16}")

    # --- 2. una especie por muestra -----------------------------------------
    generos, especies_vig = vigilados()
    muestras, conflictos = [], 0
    for clave, grupo in por_muestra.items():
        grupo.sort(key=lambda r: PRIORIDAD.get(r["fuente"], 9))
        nombres = {r["especie"] for r in grupo if r["especie"]}
        if len(nombres) > 1:
            conflictos += 1
        mejor = grupo[0]
        fila = dict(mejor)
        fila["muestra"] = clave
        fila["fuentes"] = ",".join(sorted({r["fuente"] for r in grupo}))
        fila["n_fuentes"] = len(set(r["fuente"] for r in grupo))
        # se conserva el primer dato no vacío de cualquiera de las fuentes
        for campo in COLUMNAS:
            if not fila.get(campo):
                for r in grupo:
                    if r.get(campo):
                        fila[campo] = r[campo]
                        break
        anio = re.search(r"(1[89]\d{2}|20\d{2})", fila.get("fecha", ""))
        fila["anio"] = anio.group(1) if anio and int(anio.group(1)) >= 1940 else ""
        # Se recalcula aquí, sobre el texto libre ya reunido de todas las fuentes: así
        # cambiar una regla de departamentos no obliga a repetir la descarga de 2 GB.
        # Si las fuentes discrepan, gana el valor más frecuente.
        votos = Counter(departamento(r.get("geo") or r.get("pais")) for r in grupo)
        votos.pop("", None)
        fila["departamento"] = votos.most_common(1)[0][0] if votos else ""
        muestras.append(fila)
    print(f"  muestras con la especie en disputa{miles(conflictos):>17}")

    # --- 3. patógeno o no ----------------------------------------------------
    patogenos, plantas, excluidas = [], [], []
    for m in muestras:
        if PLANTAS.match(m["especie"]):
            plantas.append(m)
        elif es_patogeno(m["especie"], generos, especies_vig):
            patogenos.append(m)
        else:
            excluidas.append(m)

    print(regla())
    print(f"  {'patógenos de humanos y animales':<34} {miles(len(patogenos)):>14}")
    print(f"  {'patógenos de plantas':<34} {miles(len(plantas)):>14}")
    print(f"  {'excluidas (ambientales, no patóg.)':<34} {miles(len(excluidas)):>14}")
    print(regla("="))
    esp = sorted({m["especie"] for m in patogenos if m["especie"]})
    print(f"  {'especies patógenas':<34} {miles(len(esp)):>14}")
    print(regla("="))

    campos = COLUMNAS + ["muestra", "fuentes", "n_fuentes", "anio"]
    for nombre, datos in (("muestras", patogenos), ("plantas", plantas),
                          ("excluidas", excluidas)):
        destino = AQUI / "results" / f"{nombre}.csv"
        with destino.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            w.writerows(datos)

    corte_f = AQUI / "results" / "corte.json"
    corte = json.loads(corte_f.read_text())
    corte["limpieza"] = {
        "registros_entrada": len(registros), "muestras_unicas": len(por_muestra),
        "colapsadas": len(registros) - len(por_muestra), "conflicto_especie": conflictos,
        "patogenos": len(patogenos), "plantas": len(plantas), "excluidas": len(excluidas),
        "especies_patogenas": len(esp), "en": ahora(),
        "top_excluidas": Counter(m["especie"] for m in excluidas).most_common(15),
    }
    corte_f.write_text(json.dumps(corte, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
