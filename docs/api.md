# API del backend

Base: `http://localhost:3001` (puerto en `PUERTO_BACKEND`). Todas las respuestas son JSON. Los errores siempre tienen la forma `{"error": "mensaje"}`.

El motor Python tiene su propia documentación interactiva en `http://localhost:8000/docs` (FastAPI). El frontend y los clientes externos solo deben hablar con este backend.

## `POST /api/agente` (lo usa la interfaz)

Conversación con el agente Lexia, que busca en el Código de Policía y el Código de Tránsito, lee artículos, calcula multas y arma casos.

**Cuerpo**

```json
{ "mensajes": [
    { "rol": "usuario", "texto": "¿Me pueden pedir la cédula en la calle?" },
    { "rol": "lexia",   "texto": "Sí, en estos casos…" },
    { "rol": "usuario", "texto": "¿Y si me niego?" }
] }
```

De 1 a 30 mensajes; el último debe ser del usuario (3 a 2000 caracteres).

**Respuesta 200** (`text/event-stream`), un JSON por evento:

```
data: {"tipo": "estado", "texto": "Buscando en el Código de Policía: “procedimiento de identificación”"}
data: {"tipo": "estado", "texto": "Leyendo el Artículo 35 del Código de Policía"}
data: {"tipo": "fuentes", "fuentes": [{"ref": "Artículo 35", "norma": "Ley 1801 de 2016", "texto": "…", "vigencia": "vigente"}]}
data: {"tipo": "respuesta", "texto": "… (Ley 1801, Art. 35, num. 3) …"}
data: {"tipo": "fin", "tiempo_ms": 4200, "modelo": "openai/gpt-oss-120b"}
```

Si falla el modelo llega `{"tipo": "error", "texto": "…"}`. Los errores de validación (400), CORS (403), límite (429) y motor caído (503) son iguales a los de `/api/chat`.

## `POST /api/adjunto`

Convierte un archivo del chat en texto para Lexia. `multipart/form-data` con el campo `archivo` (máx. 15 MB). **No se guarda**: se procesa en memoria (Ley 1581 de 2012).

| Tipo | Qué se hace |
|---|---|
| Imagen (jpg, png, webp…) | Modelo de visión (`LLM_MODELO_VISION`): transcribe el texto visible y describe la escena |
| PDF | Texto de hasta 15 páginas; si es escaneado, se analiza la primera página como imagen |
| Word (.docx), .txt, .md, .csv, .json | Texto del archivo |
| Audio o video | Transcripción de lo que se dice con Whisper (`LLM_MODELO_AUDIO`); la imagen del video no se analiza |

```json
{ "nombre": "nota.wav", "tipo": "audio", "texto": "Transcripción de lo que se dice en el audio: Me pusieron un comparendo…", "nota": "" }
```

La interfaz agrega ese texto a la pregunta como `[ARCHIVO ADJUNTO: nombre (tipo)]` y Lexia lo analiza con la ley.

## `POST /api/chat`

Responde una pregunta sobre la Ley 1801 de 2016 (RF1, RF2, RF3, RF5).

**Cuerpo**

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `pregunta` | texto | sí | entre 3 y 500 caracteres |
| `k` | entero | no | fragmentos a recuperar, de 1 a 15 (si no se envía, el motor usa 8). A estos se suman los fragmentos *relacionados* (tabla de multas del artículo, Art. 180) |
| `modo` | texto | no | `hibrido` (FAISS + BM25 con Reciprocal Rank Fusion, por defecto), `semantico` (solo FAISS) o `lexico` (solo BM25) |

```json
{ "pregunta": "¿Qué puedo hacer si no estoy de acuerdo con una orden de comparendo?", "k": 5 }
```

**Respuesta 200**

```json
{
  "pregunta": "¿Qué puedo hacer si no estoy de acuerdo con una orden de comparendo?",
  "respuesta": "… (Art. 222, par. 1) …",
  "fuentes": [
    {
      "ref": "Artículo 222, parágrafo 1",
      "articulo": 222,
      "epigrafe": "Trámite del proceso verbal inmediato",
      "texto": "…",
      "vigencia": "vigente",
      "puntaje": 0.6812
    }
  ],
  "estrategia": "estructural",
  "modelo_embeddings": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "modelo_llm": "llama-3.3-70b-versatile",
  "tiempo_ms": 2140,
  "aviso": "Herramienta informativa. No sustituye la asesoría de un abogado."
}
```

`fuentes` trae los fragmentos que usó el modelo, ordenados por `puntaje` (similitud coseno de 0 a 1), para que el usuario verifique la respuesta. Si la información no está en el Código, `respuesta` es la frase fija *"No encontré esa información en el Código Nacional de Seguridad y Convivencia Ciudadana (Ley 1801 de 2016)."*

**Errores**

| Código | Cuándo |
|---|---|
| 400 | pregunta vacía, muy larga o que no es texto; `k` fuera de rango; JSON mal formado |
| 403 | el navegador llama desde un origen no permitido por CORS |
| 429 | más de `LIMITE_CHAT_POR_MINUTO` preguntas por minuto desde la misma IP (20 por defecto) |
| 502 | el motor falló al llamar al modelo de IA (clave inválida, límite del proveedor…) |
| 503 | el motor Python no está corriendo |
| 504 | el motor tardó más de 30 s |

## `POST /upload_pdf/`

Guarda un PDF nuevo en `motor/data/pendientes/` **sin regenerar los embeddings** (RF4). Para que el chatbot lo use hay que procesarlo e indexarlo manualmente.

Petición `multipart/form-data` con el archivo en el campo `archivo`:

```bash
curl -F "archivo=@decreto.pdf;type=application/pdf" http://localhost:3001/upload_pdf/
```

**Respuesta 201**

```json
{ "mensaje": "PDF guardado. Para incluirlo en el chatbot hay que reindexar manualmente.",
  "archivo": "1762963200000_decreto.pdf", "tamano_bytes": 182344 }
```

Se valida la extensión, el tipo MIME y la firma real del archivo (`%PDF-`); el nombre se limpia para que no pueda escribir fuera de la carpeta.

| Código | Cuándo |
|---|---|
| 400 | no se envió el campo `archivo` |
| 413 | el archivo pasa de 20 MB |
| 415 | no es un PDF (o dice serlo pero su contenido no lo es) |
| 429 | más de 10 cargas por hora desde la misma IP |

## `GET /api/pendientes`

Lista los PDF cargados que esperan indexación.

```json
{ "total": 1, "archivos": [ { "archivo": "1762963200000_decreto.pdf", "tamano_bytes": 182344, "subido": "2026-11-12T15:20:00.000Z" } ] }
```

## `GET /api/health`

Estado del backend y del motor.

```json
{ "backend": "ok", "motor": { "estado": "ok", "estrategia": "estructural", "fragmentos": 1534, "modelo_embeddings": "…", "modelo_llm": "…" } }
```

Si el motor no responde, `motor` vale `"sin conexión"`.

## Seguridad y privacidad

- **CORS (RNF3):** solo los orígenes de `ORIGENES_PERMITIDOS` (separados por coma) pueden llamar desde un navegador.
- **Claves (RNF2):** el backend no maneja la clave del LLM; vive en el `.env` y solo la lee el motor.
- **Límite de peticiones:** protege la cuota de la API del modelo de IA.
- **Cabeceras de seguridad:** `helmet`.
- **Datos personales (Ley 1581 de 2012):** el registro de peticiones guarda método, ruta, código y tiempo, nunca el texto de la pregunta.

## Pruebas

```bash
cd backend
npm test
```

Las pruebas levantan un motor falso, así que no necesitan Python, FAISS ni clave de API.
