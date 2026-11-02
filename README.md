# Inventario de genomas de patógenos aislados en Colombia

Cuántos genomas de patógenos aislados **en Colombia** hay públicos ahora mismo, en qué
estado están y qué se puede hacer con ellos sin laboratorio, sin permisos y sin pagar
secuenciación.

Seis scripts de Python, cuatro bases públicas, un comando por paso. Todo corre desde una
terminal con internet.

> **Cifras de este corte:** ver `resultados/RESUMEN.json`. Las bases crecen todos los días;
> cada ejecución deja su propia fecha de corte en `resultados/corte.json`.

## Para qué sirve

Si trabajas en microbiología, salud pública o bioinformática en Colombia o en la región, y
quieres publicar sin tener muestras propias, esto te dice **dónde están los datos que ya
existen y nadie ha analizado**. En particular:

- Muestras con lecturas crudas públicas y **sin genoma ensamblado**: se pueden ensamblar,
  anotar y comparar hoy mismo.
- Muestras **sin departamento registrado**: dos de cada tres genomas públicos del país no
  dicen de qué parte vienen. Caracterizar ese sesgo es en sí mismo un resultado publicable.
- Especies vigiladas con muy pocas muestras depositadas: huecos de vigilancia genómica.

## Las cuatro fuentes

| Fuente | Qué aporta | Consulta |
| --- | --- | --- |
| **NCBI Pathogen Detection** | Aislamientos de los grupos que NCBI vigila | `latest_snps/Metadata/*.metadata.tsv` de cada grupo, filtrado por `geo_loc_name` |
| **BV-BRC** | Genomas bacterianos ensamblados | `and(eq(isolation_country,Colombia),eq(taxon_lineage_ids,2))` |
| **ENA** (incluye SRA y DDBJ) | Corridas de lecturas crudas | `country="Colombia*" AND tax_tree(2)` y `tax_tree(4751)` |
| **NCBI BioSample + Assembly** | Muestras y ensamblajes de hongos | `Colombia[All Fields] AND txid4751[Organism:exp]` |

Todas pasan por la misma regla de país: el campo debe **empezar** por «Colombia».

## Cómo se corre

```bash
pip install requests
cd scripts
./fuentes.py      # pregunta a las cuatro bases       (descarga ~2 GB, se filtra al vuelo)
./unificar.py     # las junta en una sola tabla
./limpiar.py      # una fila por muestra; solo patógenos
./estado.py       # ensambladas vs. sin ensamblar
./mapa.py         # de qué departamento vienen
```

`./fuentes.py` transmite y descarta sobre la marcha: el archivo de *Salmonella* pesa
880 MB y nunca toca el disco. Solo se guardan las filas cuyo país es Colombia.

## Las tres decisiones que cambian el número

Cualquiera que repita esta consulta se topa con las mismas tres trampas. Están resueltas en
`limpiar.py` y documentadas ahí mismo:

1. **Pedir «bacterias de Colombia» no devuelve patógenos, devuelve bacterias.** Entra
   *Candidatus Methylomirabilis* sp., aislada de suelo (PRJNA983538). El inventario se queda
   con lo que NCBI Pathogen Detection vigila más una lista de géneros clínicos; todo lo
   excluido queda listado en `resultados/excluidas.csv` para que se pueda discutir.
2. **El mismo ensamblaje, dos veces.** `GCA_x` (GenBank) y `GCF_x` (RefSeq) son el mismo
   ensamblaje. Se reducen a una clave.
3. **Especies reclasificadas.** BV-BRC todavía llama *Enterobacter cloacae* a lo que NCBI ya
   movió a *E. hormaechei*. Cuando las fuentes discrepan, manda la de taxonomía más reciente.

Una muestra es un BioSample; si falta, su ensamblaje; si falta, su primera corrida.

## Qué hay en `resultados/`

| Archivo | Qué es |
| --- | --- |
| `RESUMEN.json` | Las cifras principales del corte, para citar |
| `muestras.csv` | Una fila por muestra de patógeno, con su especie, estado y departamento |
| `plantas.csv` | Patógenos de plantas, aparte |
| `excluidas.csv` | Lo que se dejó fuera, con su especie: para auditar el criterio |
| `registros.csv` | Todo lo que devolvieron las bases antes de limpiar |
| `corte.json` | Qué se consultó, cuándo y cuántos registros devolvió cada fuente |
| `estado.json`, `mapa.json` | Las cifras de los pasos 4 y 5 |

## Limitaciones, en voz alta

- Los datos públicos describen **lo que se ha depositado**, no la prevalencia real de cada
  patógeno en Colombia. Un departamento con cero muestras no es un departamento sin
  patógenos: es un departamento sin secuenciación depositada.
- Es una foto del día del corte.
- «Patógeno» es un criterio de trabajo, no una verdad taxonómica. Las listas están al
  principio de `limpiar.py` y se pueden discutir; `excluidas.csv` existe para eso.
- Las muestras sin campo de país no entran. El inventario está sesgado hacia quien llena
  bien los metadatos.
- La asignación de departamento se hace con reglas de texto sobre un campo libre. Los casos
  ambiguos (Córdoba es departamento y también municipio del Quindío; Santander de Quilichao
  está en el Cauca) se resuelven por el orden de las reglas, no por geocodificación.

## Si encuentras un error

Abre un *issue*. En particular si una especie está mal clasificada como patógena o como
ambiental, o si una muestra quedó asignada al departamento equivocado: son las dos partes
que dependen de reglas escritas a mano.

## Cómo citarlo

Ver `CITATION.cff`. El DOI de Zenodo cita la versión congelada; este repositorio es la
versión viva.

## Licencia

Código: MIT. Datos y documentación: CC BY 4.0. Los registros originales pertenecen a NCBI,
BV-BRC y ENA y se rigen por sus propios términos.
