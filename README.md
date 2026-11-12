# Chatbot Código Nacional de Seguridad y Convivencia Ciudadana

Chatbot con arquitectura RAG que responde preguntas sobre la Ley 1801 de 2016 citando los artículos.

```
motor/      Python: corpus, análisis lingüístico, embeddings, FAISS y API (FastAPI)
backend/    Node.js + Express: API pública, CORS, /upload_pdf/
frontend/   React + Vite: interfaz de chat
evaluacion/ banco de preguntas y métricas
docs/       documentación del corpus e informes
```

## Requisitos

Python 3.11, Node.js 20 y Git.

## Instalación del motor

```bash
cd motor
python -m venv .venv
.venv\Scripts\activate          # en Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_md
```

## Construcción del corpus

1. Descargar el texto de la ley y guardarlo en `motor/data/raw/`.
2. Ejecutar:

```bash
python src/extraer_texto.py data/raw/Ley_1801_de_2016.pdf
python src/segmentar.py --fuente "Función Pública - Gestor Normativo" --url "URL_DE_DESCARGA" --fecha 2026-11-12
python src/estadisticas.py
```

Salidas en `motor/data/procesado/`: `ley1801_limpio.txt`, `corpus.json`, `estadisticas.md` y `estadisticas.json`.

## Variables de entorno

Copiar `.env.example` como `.env` y llenar las claves. El archivo `.env` no se sube al repositorio.
