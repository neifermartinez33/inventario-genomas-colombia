#!/usr/bin/env python3
"""Pregunta a las cuatro bases públicas qué tienen aislado en COLOMBIA.

Cada fuente se consulta por su campo de país y se filtra con la misma regla
(`es_colombia`). Lo que no sea de Colombia no entra al inventario.

    ./fuentes.py            todas
    ./fuentes.py ena        una sola
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from comun import ahora, construir, es_colombia, limpio, miles, regla  # noqa: E402

AQUI = Path(__file__).parent
DATOS = AQUI / "data"
CORTE = AQUI / "results" / "corte.json"
UA = {"User-Agent": "inventario-genomas-colombia/1.0 (contacto: NCBI_EMAIL)"}
TIEMPO = 180


def escribir(nombre: str, filas: list[dict]) -> Path:
    DATOS.mkdir(exist_ok=True)
    destino = DATOS / f"fuente_{nombre}.csv"
    with destino.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()) if filas else ["fuente"])
        w.writeheader()
        w.writerows(filas)
    return destino


# --- 1. ENA (incluye SRA y DDBJ) -------------------------------------------
CAMPOS_ENA = ("run_accession,sample_accession,secondary_sample_accession,study_accession,"
              "scientific_name,tax_id,country,collection_date,host,isolation_source,"
              "center_name,instrument_platform,library_source,library_strategy")


def ena(taxon: int, reino: str) -> list[dict]:
    r = requests.get("https://www.ebi.ac.uk/ena/portal/api/search", timeout=TIEMPO, headers=UA,
                     params={"result": "read_run", "format": "tsv", "limit": 0,
                             "fields": CAMPOS_ENA,
                             "query": f'country="Colombia*" AND tax_tree({taxon})'})
    r.raise_for_status()
    crudas = list(csv.DictReader(io.StringIO(r.text), delimiter="\t"))

    # Solo material genómico y secuenciación de genoma completo: RNA-Seq y amplicones
    # (16S) no sirven para ensamblar un genoma, y son la mayoría de lo que sobra.
    filas, descartadas = [], 0
    for c in crudas:
        if limpio(c.get("library_source")).upper() != "GENOMIC":
            descartadas += 1
            continue
        if limpio(c.get("library_strategy")).upper() not in {"WGS", "WGA"}:
            descartadas += 1
            continue
        if not es_colombia(c.get("country")):
            descartadas += 1
            continue
        filas.append(construir(
            fuente="ENA", especie=c.get("scientific_name"), biosample=c.get("sample_accession"),
            corridas=c.get("run_accession"), bioproject=c.get("study_accession"),
            centro=c.get("center_name"), fuente_aislamiento=c.get("isolation_source"),
            huesped=c.get("host"), fecha=c.get("collection_date"), pais=c.get("country"),
            geo=c.get("country"), taxid=c.get("tax_id"), reino=reino,
            plataforma=c.get("instrument_platform"), id_fuente=c.get("run_accession")))
    print(f"   corridas devueltas {miles(len(crudas))} · "
          f"genómicas WGS/WGA {miles(len(filas))} · fuera {miles(descartadas)}")
    return filas


# --- 2. BV-BRC --------------------------------------------------------------
CAMPOS_BVBRC = ("genome_id,genome_name,species,taxon_id,strain,isolation_country,"
                "geographic_location,collection_year,collection_date,host_name,"
                "isolation_source,biosample_accession,bioproject_accession,"
                "assembly_accession,sra_accession,sequencing_center,genome_status")


def bvbrc() -> list[dict]:
    url = "https://www.bv-brc.org/api/genome/"
    consulta = "and(eq(isolation_country,Colombia),eq(taxon_lineage_ids,2))"
    filas, fuera, inicio, pagina = [], 0, 0, 5000
    while True:
        r = requests.get(f"{url}?{consulta}&select({CAMPOS_BVBRC})&limit({pagina},{inicio})",
                         timeout=TIEMPO, headers={**UA, "Accept": "application/json"})
        r.raise_for_status()
        lote = r.json()
        if not lote:
            break
        for g in lote:
            # eq(isolation_country,Colombia) es coincidencia de TEXTO: también devuelve
            # "Mycobacterium colombiense". Aquí es donde se cae esa trampa.
            if not es_colombia(g.get("isolation_country")):
                fuera += 1
                continue
            filas.append(construir(
                fuente="BV-BRC", especie=g.get("species") or g.get("genome_name"),
                biosample=g.get("biosample_accession"), ensamblaje=g.get("assembly_accession"),
                corridas=g.get("sra_accession"), bioproject=g.get("bioproject_accession"),
                centro=g.get("sequencing_center"), fuente_aislamiento=g.get("isolation_source"),
                huesped=g.get("host_name"),
                fecha=g.get("collection_date") or g.get("collection_year"),
                pais=g.get("isolation_country"),
                geo=g.get("geographic_location") or g.get("isolation_country"),
                taxid=g.get("taxon_id"), reino="bacteria", id_fuente=g.get("genome_id")))
        inicio += pagina
        if len(lote) < pagina:
            break
    print(f"   genomas con país Colombia {miles(len(filas))} · "
          f"descartados por el filtro de país {miles(fuera)}")
    return filas


# --- 3. NCBI Pathogen Detection --------------------------------------------
FTP = "https://ftp.ncbi.nlm.nih.gov/pathogen/Results/"


def grupos_pd() -> list[str]:
    texto = requests.get(FTP, timeout=TIEMPO, headers=UA).text
    # BioProject_Hierarchy no es un grupo taxonómico: no tiene metadatos de aislamientos.
    return sorted({g for g in re.findall(r'href="([A-Za-z_]+)/"', texto)
                   if g != "BioProject_Hierarchy"})


def url_metadata(grupo: str) -> str | None:
    for sub in ("latest_snps", "latest_kmer"):
        r = requests.get(f"{FTP}{grupo}/{sub}/Metadata/", timeout=TIEMPO, headers=UA)
        if r.status_code != 200:
            continue
        m = re.search(r'href="([^"]*\.metadata\.tsv)"', r.text)
        if m:
            return f"{FTP}{grupo}/{sub}/Metadata/{m.group(1)}"
    return None


def pathogen_detection() -> list[dict]:
    grupos = grupos_pd()
    filas, bytes_vistos, sin_metadatos = [], 0, []
    for i, grupo in enumerate(grupos, 1):
        url = url_metadata(grupo)
        if not url:
            sin_metadatos.append(grupo)
            continue
        # Se transmite y se filtra al vuelo: el archivo de Salmonella pesa 880 MB y
        # nunca toca el disco. Solo sobreviven las filas cuyo país es Colombia.
        with requests.get(url, timeout=TIEMPO, headers=UA, stream=True) as r:
            r.raise_for_status()
            lector = csv.DictReader(
                (l.decode("utf-8", "replace") for l in r.iter_lines() if l), delimiter="\t")
            for fila in lector:
                bytes_vistos += 1
                if not es_colombia(fila.get("geo_loc_name")):
                    continue
                filas.append(construir(
                    fuente="NCBI Pathogen Detection",
                    especie=fila.get("scientific_name"), biosample=fila.get("biosample_acc"),
                    ensamblaje=fila.get("asm_acc"), corridas=fila.get("Run"),
                    bioproject=fila.get("bioproject_acc"),
                    centro=fila.get("bioproject_center") or fila.get("sra_center"),
                    fuente_aislamiento=fila.get("isolation_source"), huesped=fila.get("host"),
                    fecha=fila.get("collection_date"), pais=fila.get("geo_loc_name"),
                    geo=fila.get("geo_loc_name"), taxid=fila.get("taxid"),
                    reino="hongo" if "Candidozyma" in grupo or "Candida" in grupo else "bacteria",
                    plataforma=fila.get("Platform"), id_fuente=fila.get("target_acc")))
        print(f"   [{i:>3}/{len(grupos)}] {grupo[:30]:<30} "
              f"Colombia: {miles(len(filas))}", flush=True)
    if sin_metadatos:
        print(f"   grupos sin archivo de metadatos: {', '.join(sin_metadatos)}")
    print(f"   aislamientos revisados {miles(bytes_vistos)} · de Colombia {miles(len(filas))}")
    return filas


# --- 4. NCBI BioSample + Assembly, hongos ----------------------------------
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def ncbi_hongos() -> list[dict]:
    consulta = "Colombia[All Fields] AND txid4751[Organism:exp]"
    r = requests.get(f"{EUTILS}esearch.fcgi", timeout=TIEMPO, headers=UA,
                     params={"db": "biosample", "term": consulta, "retmax": 10000,
                             "retmode": "json"})
    r.raise_for_status()
    ids = r.json()["esearchresult"]["idlist"]
    print(f"   BioSample devuelve {miles(len(ids))} muestras de hongos")

    filas = []
    for i in range(0, len(ids), 300):
        lote = ids[i:i + 300]
        r = requests.post(f"{EUTILS}efetch.fcgi", timeout=TIEMPO, headers=UA,
                          data={"db": "biosample", "id": ",".join(lote), "rettype": "full",
                                "retmode": "xml"})
        r.raise_for_status()
        for bloque in re.split(r"<BioSample ", r.text)[1:]:
            acc = re.search(r'accession="(SAM[^"]+)"', bloque)
            pais = re.search(r'attribute_name="geo_loc_name"[^>]*>([^<]*)<', bloque) or \
                   re.search(r'harmonized_name="geo_loc_name"[^>]*>([^<]*)<', bloque)
            if not acc or not pais or not es_colombia(pais.group(1)):
                continue
            def attr(nombre: str) -> str:
                m = re.search(rf'harmonized_name="{nombre}"[^>]*>([^<]*)<', bloque)
                return m.group(1) if m else ""
            org = re.search(r"<OrganismName>([^<]+)</OrganismName>", bloque)
            proy = re.search(r">(PRJ[A-Z]{2}\d+)<", bloque)
            filas.append(construir(
                fuente="NCBI BioSample", especie=org.group(1) if org else "",
                biosample=acc.group(1), bioproject=proy.group(1) if proy else "",
                fuente_aislamiento=attr("isolation_source"), huesped=attr("host"),
                fecha=attr("collection_date"), pais=pais.group(1), geo=pais.group(1),
                reino="hongo", id_fuente=acc.group(1)))
        time.sleep(0.4)      # cortesía con E-utilities
    print(f"   de Colombia {miles(len(filas))}")

    # Ensamblajes de hongos: se cruza el resumen de RefSeq/GenBank por país de la muestra.
    r = requests.get("https://ftp.ncbi.nlm.nih.gov/genomes/ASSEMBLY_REPORTS/"
                     "assembly_summary_genbank.txt", timeout=TIEMPO, headers=UA, stream=True)
    r.raise_for_status()
    de_colombia = {f["biosample"] for f in filas if f["biosample"]}
    ensamblajes, encabezado = 0, None
    for linea in r.iter_lines():
        texto = linea.decode("utf-8", "replace")
        if texto.startswith("#assembly_accession"):
            encabezado = texto.lstrip("#").split("\t")
            continue
        if texto.startswith("#") or not encabezado:
            continue
        campos = dict(zip(encabezado, texto.split("\t")))
        if campos.get("biosample") in de_colombia:
            for f in filas:
                if f["biosample"] == campos["biosample"] and not f["ensamblaje"]:
                    f["ensamblaje"] = campos["assembly_accession"]
                    f["fuente"] = "NCBI Assembly"
                    ensamblajes += 1
                    break
    print(f"   con ensamblaje público {miles(ensamblajes)}")
    return filas


FUENTES = {
    "ena":      ("ENA · corridas de lecturas crudas", lambda: ena(2, "bacteria") + ena(4751, "hongo")),
    "bvbrc":    ("BV-BRC · genomas bacterianos ensamblados", bvbrc),
    "pd":       ("NCBI Pathogen Detection · aislamientos vigilados", pathogen_detection),
    "hongos":   ("NCBI BioSample y Assembly · hongos", ncbi_hongos),
}


def main() -> int:
    pedidas = sys.argv[1:] or list(FUENTES)
    corte = json.loads(CORTE.read_text()) if CORTE.exists() else {}
    corte.setdefault("fuentes", {})
    print(regla("="))
    print("INVENTARIO DE GENOMAS AISLADOS EN COLOMBIA".center(51))
    print(regla("="))
    for clave in pedidas:
        titulo, funcion = FUENTES[clave]
        print(f"\n▸ {titulo}")
        t0 = time.time()
        filas = funcion()
        destino = escribir(clave, filas)
        corte["fuentes"][clave] = {
            "titulo": titulo, "registros": len(filas),
            "consultado_en": ahora(), "segundos": round(time.time() - t0, 1),
            "archivo": destino.name,
        }
        print(f"   → {destino.name}  {miles(len(filas))} registros  "
              f"{time.time() - t0:.0f}s")
    corte["fecha_corte"] = ahora()
    CORTE.parent.mkdir(exist_ok=True)
    CORTE.write_text(json.dumps(corte, ensure_ascii=False, indent=2))
    total = sum(f["registros"] for f in corte["fuentes"].values())
    print(f"\n{regla()}\nTOTAL  {miles(total)} registros de Colombia\n{regla()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
