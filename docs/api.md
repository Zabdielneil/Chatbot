# API del backend

Base: `http://localhost:3001` (puerto en `PUERTO_BACKEND`). Todas las respuestas son JSON. Los errores siempre tienen la forma `{"error": "mensaje"}`.

El motor Python tiene su propia documentación interactiva en `http://localhost:8000/docs` (FastAPI). El frontend y los clientes externos solo deben hablar con este backend.

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
