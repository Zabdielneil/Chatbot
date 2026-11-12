# Chatbot Código Nacional de Seguridad y Convivencia Ciudadana

Chatbot con arquitectura RAG que responde preguntas sobre la Ley 1801 de 2016 citando los artículos.

```
motor/      Python: corpus, análisis lingüístico, embeddings, FAISS, RAG y API (FastAPI)
backend/    Node.js + Express: API pública, CORS, /api/chat, /upload_pdf/
frontend/   React + Vite: interfaz de chat (pendiente)
evaluacion/ banco de preguntas y métricas (pendiente)
docs/       corpus.md, arquitectura.md
```

Arquitectura completa: [docs/arquitectura.md](docs/arquitectura.md)

## Requisitos

Python 3.11, Node.js 20 y Git.

## 1. Instalación

```bash
# motor (Python)
cd motor
python -m venv .venv
.venv\Scripts\activate          # en Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md

# backend (Node)
cd ../backend
npm install
```

Copiar `.env.example` como `.env` en la raíz del repo y poner la `LLM_API_KEY`.

## 2. Construir el corpus (desde `motor/`)

1. Descargar la ley y guardarla en `motor/data/raw/Ley_1801_de_2016.pdf`.
2. Ejecutar:

```bash
python src/extraer_texto.py data/raw/Ley_1801_de_2016.pdf
python src/segmentar.py --fuente "Función Pública - Gestor Normativo" --url "URL_DE_DESCARGA" --fecha 2026-11-12
python src/estadisticas.py
```

Salidas en `motor/data/procesado/`: `ley1801_limpio.txt`, `corpus.json`, `estadisticas.md` y `estadisticas.json`.

## 3. Embeddings e índice FAISS (desde `motor/`)

```bash
python src/indexar.py --estrategia todas
```

Genera `data/indice/estructural.faiss` y `data/indice/fija.faiss` con sus fragmentos. La primera vez descarga el modelo de embeddings (~470 MB).

## 4. Probar el RAG en la terminal (desde `motor/`)

```bash
python src/rag.py "¿Qué es una orden de comparendo?" --solo-buscar    # solo FAISS
python src/rag.py "¿Cuánto es la multa por orinar en la calle?"       # FAISS + modelo de IA
```

## 5. Levantar los servicios

```bash
# terminal 1 – motor (desde motor/, con el .venv activo)
uvicorn src.api:app --reload --port 8000        # docs en http://localhost:8000/docs

# terminal 2 – backend (desde backend/)
npm run dev                                     # http://localhost:3001
```

Endpoints del backend:

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/chat` | Body `{"pregunta": "...", "k": 5}` → respuesta, fuentes y tiempo |
| POST | `/upload_pdf/` | Form-data con campo `archivo` (PDF). Lo guarda sin reindexar |
| GET | `/api/health` | Estado del backend y del motor |

## Variables de entorno

Ver `.env.example`. El archivo `.env` no se sube al repositorio.
