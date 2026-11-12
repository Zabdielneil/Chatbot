# Documentación del corpus – Ley 1801 de 2016

## Origen

El corpus se construyó a partir del texto de la Ley 1801 de 2016, por la cual se expide el Código Nacional de Seguridad y Convivencia Ciudadana. Se tomó la versión publicada en [FUENTE: Función Pública – Gestor Normativo / Secretaría del Senado / SUIN-Juriscol], disponible en [URL], y la consulta se hizo el [FECHA DE CONSULTA]. Elegimos esta fuente porque es oficial y porque incluye las notas de vigencia de cada artículo, lo que nos permitió marcar cuáles fueron modificados por leyes posteriores (por ejemplo la Ley 2000 de 2019) o tuvieron pronunciamientos de la Corte Constitucional.

## Limpieza

El texto se extrajo con PyMuPDF (o BeautifulSoup si se usa la versión HTML) y se limpió con el script `motor/src/extraer_texto.py`. Ahí se eliminan los encabezados y pies que se repiten en cada página, la numeración de páginas, las URL, las fechas de impresión y los caracteres corruptos o invisibles, y también se unen las palabras que quedaban partidas con guion al final de una línea. El resultado queda en `motor/data/procesado/ley1801_limpio.txt`.

## Criterios de segmentación

La segmentación se hace con expresiones regulares en `motor/src/segmentar.py` siguiendo la estructura jerárquica de la ley: libro, título, capítulo y artículo. Dentro de cada artículo se separa el inciso principal, los numerales y los parágrafos. Para no confundir las referencias internas (por ejemplo "conforme al artículo 140") con el inicio de un artículo nuevo, solo se acepta como artículo una línea que empieza por ARTÍCULO y cuyo número sigue la secuencia del anterior. Las notas de vigencia y los textos de legislación anterior se sacan del cuerpo del artículo y se guardan aparte para que el chatbot no responda con texto que ya no está vigente.

## Metadatos de cada fragmento

Cada artículo en `corpus.json` tiene un identificador (`art_N`), el número de artículo, el epígrafe, el libro, título y capítulo con sus nombres, el texto completo, el inciso, la lista de numerales y de parágrafos, las notas de vigencia, un estado de vigencia (vigente, vigente con cambios o derogado), las observaciones encontradas (modificado, adicionado, inexequible, exequibilidad condicionada), las leyes modificatorias y sentencias mencionadas, los temas asignados por palabras clave y el número de palabras.

El estado de vigencia se asigna de forma automática a partir de las notas, por eso los artículos marcados como "vigente con cambios" se revisaron manualmente contra la fuente. [ANOTAR AQUÍ LOS QUE SE REVISARON Y QUÉ SE CORRIGIÓ.]

## Licencia de uso

Las leyes colombianas son de libre reproducción siempre que se respete el texto de la edición oficial (Ley 23 de 1982, artículo 41) [VERIFICAR LA CITA]. El corpus se usa con fines académicos y el chatbot es una herramienta informativa que no reemplaza la asesoría de un abogado.

## Resultados

[PEGAR AQUÍ LA SALIDA DE `segmentar.py`: total de artículos, distribución por libro, parágrafos, numerales y estado de vigencia.]
