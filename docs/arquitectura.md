# Arquitectura propuesta – Chatbot RAG Ley 1801 de 2016

## Diagrama

```mermaid
flowchart LR
    U([Ciudadano]) --> FE

    subgraph FE[Frontend · React + Vite]
        CHAT[Chat con historial]
        SRC[Panel de fuentes citadas]
        AV[Aviso: no es asesoría jurídica]
    end

    FE -- "POST /api/chat" --> BE

    subgraph BE[Backend · Node.js + Express]
        CORS[CORS · orígenes del .env]
        PROXY[/api/chat → motor/]
        UP[/upload_pdf/ · multer/]
    end

    UP -. "guarda PDF sin reindexar (RF4)" .-> PEND[(data/pendientes)]
    PROXY -- "POST /query" --> API

    subgraph MOTOR[Motor documental · Python]
        API[FastAPI]
        GLO[Glosario coloquial<br/>expansión de consulta]
        EMB[Embeddings<br/>paraphrase-multilingual-MiniLM-L12-v2]
        IDX[(Índice FAISS<br/>IndexFlatIP · coseno)]
        BM[(BM25<br/>palabras clave)]
        RRF[Fusión RRF<br/>+ parágrafos y medidas relacionadas<br/>+ Art. 180 valores de multa]
        PROMPT[Prompt RAG<br/>solo contexto + citar artículos]
        API --> GLO
        GLO --> EMB --> IDX --> RRF
        GLO --> BM --> RRF
        RRF -- "top-k fragmentos" --> PROMPT
    end

    PROMPT -- "contexto + pregunta" --> LLM[[Modelo de IA vía API<br/>Groq / Gemini / OpenAI]]
    LLM -- "respuesta con citas" --> API

    subgraph OFF[Proceso offline · se corre una vez]
        RAW[Ley 1801 PDF/HTML<br/>Función Pública] --> EXT[extraer_texto.py<br/>limpieza]
        EXT --> SEG[segmentar.py<br/>libro › título › capítulo › artículo]
        SEG --> CORP[(corpus.json<br/>+ metadatos y vigencia)]
        CORP --> IND[indexar.py<br/>fragmentos + embeddings]
    end
    IND --> IDX
```

## Componentes

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Corpus | PyMuPDF, regex | Extraer y limpiar la ley, segmentarla por jerarquía y guardar `corpus.json` con metadatos (ubicación, epígrafe, vigencia, temas). |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` | Convertir cada fragmento y cada pregunta en un vector de 384 dimensiones. |
| Índice semántico | FAISS `IndexFlatIP` | Búsqueda exacta por similitud coseno de los fragmentos más cercanos en significado. |
| Índice léxico | BM25 (`rank-bm25`) | Búsqueda por palabras clave; complementa a FAISS en términos jurídicos exactos. |
| Glosario | Diccionario de sinónimos | Traduce expresiones ciudadanas ("orinar en la calle", "parte", "pelea") a términos de la ley. |
| Generación | LLM por API compatible con OpenAI | Redactar la respuesta usando solo los fragmentos recuperados y citando artículos. |
| Motor API | FastAPI | Endpoints `/query` (RAG completo), `/buscar` (solo recuperación) y `/health`. |
| Backend | Node.js + Express | API pública: CORS, `/api/chat`, `/upload_pdf/`, manejo de errores y `.env`. |
| Frontend | React + Vite | Chat, historial, fuentes verificables y aviso legal. |

## Flujo de una consulta

1. El ciudadano escribe la pregunta en el chat.
2. El frontend la envía a `POST /api/chat` del backend.
3. El backend valida la entrada y la reenvía a `POST /query` del motor.
4. La pregunta se expande con el glosario coloquial (por ejemplo, "orinar" → "necesidades fisiológicas", "calle" → "espacio público").
5. FAISS (por significado) y BM25 (por palabras) buscan 40 candidatos cada uno; se fusionan con Reciprocal Rank Fusion y se toman los k = 8 mejores.
6. Se agregan fragmentos relacionados: el parágrafo con la tabla de medidas de cada numeral encontrado, la medida exacta de ese numeral y, si aparece una "Multa General tipo X", el Art. 180 con su valor.
7. Se arma el prompt: instrucciones + fragmentos numerados con su referencia, vigencia y medida correctiva + pregunta.
8. El LLM responde citando los artículos, o dice que la información no está en el Código.
9. La respuesta y las fuentes vuelven al frontend, que muestra ambas.

## Decisiones de diseño

**Modelo de embeddings.** Elegimos `paraphrase-multilingual-MiniLM-L12-v2` porque está entrenado para similitud semántica en más de 50 idiomas, incluido el español, corre localmente sin costo y genera vectores pequeños (384 dimensiones) que hacen la búsqueda rápida. Su límite es de 128 tokens por texto, por eso el corpus no se indexa por artículo completo sino en fragmentos más cortos.

**Segmentación (dos estrategias a comparar).**
- *Estructural*: un fragmento por inciso, por numeral y por parágrafo. A cada numeral se le antepone el número de artículo, el epígrafe y el inicio del inciso para que no pierda el contexto.
- *Fija*: ventanas de 120 palabras con 30 de solapamiento, sin cruzar artículos.

Las dos se construyen con `python src/indexar.py --estrategia todas` y se comparan en la fase de evaluación con Precisión@k, Recall@k y MRR.

**Limpieza: ligaduras tipográficas.** El PDF de Función Pública escribe "ﬁ" y "ﬂ" como un solo carácter (U+FB01, U+FB02). Eso hacía que "ﬁsiológicas" no coincidiera con "fisiológicas" ni en BM25 ni en los embeddings. Se normalizan en `extraer_texto.py`.

**Búsqueda híbrida.** Solo con embeddings, la pregunta "¿Cuánto es la multa por orinar en la calle?" recuperaba artículos genéricos de multas, porque el ciudadano no usa el lenguaje de la ley. Con el glosario, BM25 y la fusión RRF se recupera el Art. 140, numeral 11 y su medida correctiva.

**Índice FAISS.** Con unos cientos o pocos miles de fragmentos, `IndexFlatIP` hace búsqueda exacta en milisegundos, así que no hace falta un índice aproximado (IVF o HNSW). Los vectores se normalizan, con lo que el producto interno equivale a la similitud coseno.

**Modelo de IA.** Se usa `openai/gpt-oss-120b` en Groq (capa gratuita, ~1,5 s por respuesta, menos de los 10 s del RNF1). El motor usa el cliente de OpenAI con `LLM_BASE_URL` configurable, así el mismo código funciona con Groq, Gemini u OpenAI cambiando solo el `.env`. La temperatura es 0.1 para reducir respuestas creativas.

**Control de alucinaciones.** El prompt obliga a responder solo con el contexto, citar artículo, numeral o parágrafo, advertir la vigencia y responder con una frase fija cuando la información no está en el Código (RF2, RF3).

**Seguridad.** Las claves viven en `.env`, que no se sube al repositorio (RNF2). El backend solo acepta los orígenes configurados en CORS (RNF3) y el endpoint de carga solo acepta PDF de hasta 20 MB.

## Próximos pasos

- Ampliar el glosario coloquial con el análisis lingüístico de la Fase 2.
- Clasificador temático para filtrar por libro o título antes de buscar.
- Frontend en React con panel de fuentes.
- Banco de 50 preguntas y evaluación con métricas.
