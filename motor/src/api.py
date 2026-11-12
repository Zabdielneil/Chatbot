"""Paso 6: API del motor (FastAPI). La consume el backend de Node.

Uso (desde la carpeta motor/ con el .venv activado):
    uvicorn src.api:app --reload --port 8000
Documentación automática: http://localhost:8000/docs
"""
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag import Motor  # noqa: E402

app = FastAPI(title="Motor RAG - Código Nacional de Policía",
              description="Búsqueda híbrida (FAISS + BM25 + glosario coloquial) y respuesta con modelo de IA, citando artículos de la Ley 1801 de 2016")

# el motor solo debería recibir llamadas del backend de Node
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("URL_BACKEND", "http://localhost:3001")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

motor = Motor()


class Consulta(BaseModel):
    pregunta: str = Field(..., min_length=3, max_length=500,
                          examples=["¿Cuánto es la multa por orinar en la vía pública?"])
    k: int = Field(8, ge=1, le=15)
    modo: Literal["hibrido", "semantico", "lexico"] = "hibrido"


@app.get("/health")
def health():
    return {"estado": "ok", "estrategia": motor.estrategia, "fragmentos": len(motor.fragmentos),
            "modelo_embeddings": motor.nombre_modelo, "modelo_llm": motor.modelo_llm or None}


@app.post("/buscar")
def buscar(c: Consulta):
    """Solo recuperación: devuelve los k fragmentos más parecidos (sin modelo de IA)."""
    return {"pregunta": c.pregunta, "fuentes": motor.buscar(c.pregunta, c.k, c.modo)}


@app.post("/query")
def query(c: Consulta):
    """RAG completo: recupera los fragmentos y genera la respuesta citando artículos."""
    try:
        return motor.preguntar(c.pregunta, c.k, c.modo)
    except Exception as e:  # p. ej. clave inválida o límite de la API del LLM
        raise HTTPException(status_code=502, detail=f"Error llamando al modelo de IA: {e}")
