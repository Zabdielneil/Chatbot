# Documentación del corpus – Ley 1801 de 2016

## Origen

El corpus se construyó a partir del texto de la Ley 1801 de 2016, por la cual se expide el Código Nacional de Seguridad y Convivencia Ciudadana. Se tomó la compilación publicada por la Policía Nacional de Colombia, disponible en https://www.policia.gov.co/sites/default/files/2025-07/Ley_1801_de_2016_0.pdf, y la consulta se hizo el 2026-11-12. Elegimos esta fuente porque es institucional e incluye las notas de vigencia dentro del texto de cada artículo, lo que nos permitió marcar cuáles fueron modificados por leyes posteriores (por ejemplo la Ley 2000 de 2019 y la Ley 2197 de 2022) o tuvieron pronunciamientos de la Corte Constitucional. El enunciado sugiere Secretaría del Senado, SUIN-Juriscol o Función Pública; si el docente lo exige, el mismo proceso funciona con el PDF o HTML de esas fuentes.

## Limpieza

El texto se extrajo con PyMuPDF (o BeautifulSoup si se usa la versión HTML) y se limpió con el script `motor/src/extraer_texto.py`. Ahí se eliminan los encabezados y pies que se repiten en cada página, la numeración de páginas, las URL, las fechas de impresión y los caracteres corruptos o invisibles, y también se unen las palabras que quedaban partidas con guion al final de una línea. El resultado queda en `motor/data/procesado/ley1801_limpio.txt`.

## Criterios de segmentación

La segmentación se hace con expresiones regulares en `motor/src/segmentar.py` siguiendo la estructura jerárquica de la ley: libro, título, capítulo y artículo. La edición usada no rotula los títulos con "TÍTULO X": solo escribe su nombre en mayúsculas antes del primer capítulo o artículo. Por eso el script los reconoce como una línea en mayúsculas seguida de un CAPÍTULO o un ARTÍCULO y los numera en orden dentro de cada libro (Libro Primero: 2 títulos, Libro Segundo: 15, Libro Tercero: 3). Las firmas finales de la ley se excluyen del Art. 243. Dentro de cada artículo se separa el inciso principal, los numerales y los parágrafos. Para no confundir las referencias internas (por ejemplo "conforme al artículo 140") con el inicio de un artículo nuevo, solo se acepta como artículo una línea que empieza por ARTÍCULO y cuyo número sigue la secuencia del anterior. Las notas de vigencia y los textos de legislación anterior se sacan del cuerpo del artículo y se guardan aparte para que el chatbot no responda con texto que ya no está vigente.

## Metadatos de cada fragmento

Cada artículo en `corpus.json` tiene un identificador (`art_N`), el número de artículo, el epígrafe, el libro, título y capítulo con sus nombres, el texto completo, el inciso, la lista de numerales y de parágrafos, las notas de vigencia, un estado de vigencia (vigente, vigente con cambios o derogado), las observaciones encontradas (modificado, adicionado, inexequible, exequibilidad condicionada), las leyes modificatorias y sentencias mencionadas, los temas asignados por palabras clave y el número de palabras.

## Notas de vigencia

La fuente escribe las notas entre paréntesis dentro del texto, por ejemplo "(Declarado INEXEQUIBLE mediante Sentencia de la Corte Constitucional C-223 de 2017)" o "(Numeral adicionado por el Art. 2 de la Ley 2000 de 2019)". El script las saca del texto (para que el chatbot no las lea como norma) y las guarda en `notas_vigencia`. Con ellas asigna la vigencia en dos niveles:

- **Unidad** (inciso, numeral o parágrafo): `vigente`, `modificado`, `exequibilidad condicionada`, `inexequible parcial` (solo algunas expresiones, que en el PDF estaban subrayadas y el subrayado se pierde al extraer el texto) o `inexequible`.
- **Artículo**: una nota al final del artículo que no nombra una unidad concreta se aplica al artículo completo; si dice inexequible o derogado, todas sus unidades lo heredan.

Cada fragmento del índice lleva la vigencia de su unidad, el prompt obliga al modelo a advertir cuando una norma fue declarada inexequible y la búsqueda híbrida baja en el ranking esos fragmentos (`PESO_INEXEQUIBLE`).

Limitación: la vigencia se asigna automáticamente; los artículos marcados como inexequibles (Título VI, Arts. 47 a 75, y Art. 162) y los de "inexequible parcial" deben revisarse a mano contra la sentencia correspondiente.

## Licencia de uso

Las leyes colombianas son de libre reproducción siempre que se respete el texto de la edición oficial (Ley 23 de 1982, artículo 41) [VERIFICAR LA CITA]. El corpus se usa con fines académicos y el chatbot es una herramienta informativa que no reemplaza la asesoría de un abogado.

## Resultados

Salida de `python src/segmentar.py` (2026-11-12):

| Medida | Valor |
|---|---|
| Artículos | 243 de 243 (ninguno faltante) |
| Por libro | Primero 23, Segundo 125, Tercero 95 |
| Títulos | Primero 2, Segundo 15, Tercero 3 (todos los artículos con título) |
| Numerales / parágrafos | 597 / 260 |
| Vigencia por artículo | vigente 180, vigente con cambios 33, inexequible 30 |
| Vigencia de numerales y parágrafos | vigente 702, modificado 32, exequibilidad condicionada 3, inexequible parcial 4, inexequible 116 |

Fragmentos indexados: 1.100 con la estrategia estructural y 607 con ventanas fijas de 120 palabras. Las estadísticas lingüísticas están en `motor/data/procesado/estadisticas.md`.
