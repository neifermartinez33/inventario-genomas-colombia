"""Piezas compartidas del inventario de genomas de patógenos aislados en Colombia.

Mejora la metodología del 2026-11-02 en cuatro cosas:
  1. Corre entero desde una terminal con internet; ya no hace falta Google Colab.
  2. La lista de "qué vigila NCBI" se deriva de los nombres de los grupos de Pathogen
     Detection en vez de escribirse a mano, así que se actualiza sola.
  3. Cada paso deja su fecha de corte: las bases crecen (BioSample pasó de 670 a 704
     muestras de hongos entre el 2 y el 3 de noviembre de 2026).
  4. Las descargas grandes se transmiten y se filtran al vuelo: nunca tocan el disco.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

# --- país -------------------------------------------------------------------
# El campo de país debe EMPEZAR por "Colombia". Sin este ancla entran cosas como
# "Mycobacterium colombiense", que es justo lo que devuelve la API de BV-BRC cuando
# se le pide isolation_country=Colombia: su eq() hace coincidencia de texto.
PATRON_COLOMBIA = re.compile(r"^\s*colombia\b", re.IGNORECASE)

VACIOS = {"", "na", "n/a", "none", "null", "-", "missing", "not collected",
          "not applicable", "unknown", "not determined", "not provided",
          "restricted access", "not available"}


def limpio(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto.lower() in VACIOS else texto


def es_colombia(valor) -> bool:
    texto = limpio(valor)
    return bool(texto and PATRON_COLOMBIA.match(texto))


# --- especies ---------------------------------------------------------------
RUIDO_ESPECIE = re.compile(
    r"\b(subsp|serovar|serotype|str|strain|var|pv|bv|complex|group|sp|spp)\b.*",
    re.IGNORECASE)

# Nombres nuevos de las levaduras tras la revisión de 2024: el mismo organismo aparece
# con los dos nombres según la fuente, y si no se unen se cuenta dos veces.
SINONIMOS = {
    "Candidozyma auris": "Candida auris",
    "Nakaseomyces glabratus": "Candida glabrata",
    "Pichia kudriavzevii": "Candida krusei",
    "Clavispora lusitaniae": "Candida lusitaniae",
    "Meyerozyma guilliermondii": "Candida guilliermondii",
    "Raoultella planticola": "Klebsiella planticola",
    "Raoultella terrigena": "Klebsiella terrigena",
    "Raoultella ornithinolytica": "Klebsiella ornithinolytica",
}


def especie_estandar(nombre) -> str:
    """Deja género y especie, sin serovar ni cepa, y unifica sinónimos."""
    texto = limpio(nombre)
    if not texto:
        return ""
    texto = RUIDO_ESPECIE.sub("", texto).strip()
    partes = texto.replace("[", "").replace("]", "").split()
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0].capitalize()
    genero, epiteto = partes[0].capitalize(), partes[1].lower()
    if not re.fullmatch(r"[a-z-]+", epiteto):       # "sp.", "cf.", códigos de cepa
        return genero
    return SINONIMOS.get(f"{genero} {epiteto}", f"{genero} {epiteto}")


# --- ensamblajes ------------------------------------------------------------
def clave_ensamblaje(acc) -> str:
    """GCA_000001.1 y GCF_000001.1 son el mismo ensamblaje depositado en GenBank y en
    RefSeq. Se reducen a una sola clave, sin prefijo y sin versión."""
    texto = limpio(acc)
    if not texto:
        return ""
    texto = texto.split(",")[0].strip()
    m = re.match(r"GC[AF]_(\d+)", texto, re.IGNORECASE)
    return f"GC_{m.group(1)}" if m else texto


# --- departamentos ----------------------------------------------------------
def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


# El orden importa: lo ambiguo va primero. "Santander de Quilichao" es del Cauca, no de
# Santander; "Córdoba" es también un municipio del Quindío.
REGLAS_DEPTO: list[tuple[str, str]] = [
    (r"santander de quilichao|quilichao|popayan|cauca\b", "Cauca"),
    (r"norte de santander|cucuta|pamplona|ocana", "Norte de Santander"),
    (r"quindio|armenia|salento|pijao|circasia|calarca|montenegro\b", "Quindío"),
    # Bogotá es Distrito Capital: no es parte de Cundinamarca y se cuenta aparte.
    (r"bogota|distrito capital|\bd\.?c\.?\b", "Bogotá D.C."),
    (r"cundinamarca|soacha|zipaquira|fusagasuga|girardot|chia\b|facatativa|mosquera", "Cundinamarca"),
    (r"medellin|antioquia|rionegro|bello|itagui|envigado|apartado|turbo\b", "Antioquia"),
    (r"barranquilla|atlantico|soledad|malambo", "Atlántico"),
    (r"cartagena|bolivar|magangue|turbaco", "Bolívar"),
    (r"santa marta|magdalena|cienaga\b|fundacion", "Magdalena"),
    (r"valledupar|cesar\b|aguachica", "Cesar"),
    (r"monteria|cordoba|cerete|sahagun|lorica|tierralta|planeta rica", "Córdoba"),
    (r"sincelejo|sucre\b|corozal", "Sucre"),
    (r"riohacha|guajira|maicao|uribia", "La Guajira"),
    (r"bucaramanga|santander|floridablanca|barrancabermeja|giron\b|piedecuesta", "Santander"),
    (r"cali\b|valle del cauca|palmira|buenaventura|tulua|buga\b|cartago", "Valle del Cauca"),
    (r"pasto\b|narino|tumaco|ipiales", "Nariño"),
    (r"manizales|caldas|la dorada|chinchina", "Caldas"),
    (r"pereira|risaralda|dosquebradas|santa rosa de cabal", "Risaralda"),
    (r"ibague|tolima|espinal|honda\b|melgar", "Tolima"),
    (r"neiva|huila|pitalito|garzon", "Huila"),
    (r"villavicencio|meta\b|acacias|granada\b", "Meta"),
    (r"yopal|casanare|aguazul", "Casanare"),
    (r"arauca", "Arauca"),
    (r"tunja|boyaca|duitama|sogamoso|chiquinquira", "Boyacá"),
    (r"quibdo|choco\b", "Chocó"),
    (r"florencia|caqueta", "Caquetá"),
    (r"mocoa|putumayo|puerto asis", "Putumayo"),
    (r"leticia|amazonas", "Amazonas"),
    (r"san andres|providencia", "San Andrés y Providencia"),
    (r"inirida|guainia", "Guainía"),
    (r"mitu\b|vaupes", "Vaupés"),
    (r"puerto carreno|vichada", "Vichada"),
    (r"san jose del guaviare|guaviare", "Guaviare"),
    (r"\bhuila\b", "Huila"),
    (r"ariguani|pivijay", "Magdalena"),
]
REGLAS_DEPTO_C = [(re.compile(p), d) for p, d in REGLAS_DEPTO]


def departamento(geo) -> str:
    """'Colombia: Medellin, Antioquia' -> 'Antioquia'. Vacío si no se puede decidir."""
    texto = limpio(geo)
    if not texto:
        return ""
    texto = sin_tildes(texto).lower()
    texto = re.sub(r"^\s*colombia\s*[:,]?\s*", "", texto)
    if not texto.strip():
        return ""
    for patron, depto in REGLAS_DEPTO_C:
        if patron.search(texto):
            return depto
    return ""


# --- formato común ----------------------------------------------------------
COLUMNAS = ["fuente", "especie", "especie_cruda", "biosample", "ensamblaje", "corridas",
            "bioproject", "centro", "fuente_aislamiento", "huesped", "fecha", "pais",
            "geo", "departamento", "taxid", "reino", "plataforma", "id_fuente"]


def construir(**campos) -> dict:
    fila = {c: "" for c in COLUMNAS}
    for k, v in campos.items():
        if k in fila:
            fila[k] = limpio(v)
    fila["especie_cruda"] = fila["especie_cruda"] or fila["especie"]
    fila["especie"] = especie_estandar(fila["especie"])
    fila["ensamblaje"] = clave_ensamblaje(fila["ensamblaje"])
    fila["departamento"] = departamento(fila["geo"] or fila["pais"])
    return fila


def muestra_id(fila: dict) -> str:
    """Una muestra es un BioSample. Si falta, su ensamblaje. Si falta, su primera corrida."""
    if fila.get("biosample"):
        return fila["biosample"].split(",")[0].strip()
    if fila.get("ensamblaje"):
        return fila["ensamblaje"]
    if fila.get("corridas"):
        return fila["corridas"].split(",")[0].strip()
    return f"{fila.get('fuente','?')}:{fila.get('id_fuente','?')}"


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


ANCHO = 51   # columnas de la terminal que se ve en el video


def regla(caracter: str = "─") -> str:
    return caracter * ANCHO
