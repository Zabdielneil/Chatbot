"""Paso 6: API del motor (FastAPI). La consume el backend de Node.

Uso (desde la carpeta motor/ con el .venv activado):
    uvicorn src.api:app --reload --port 8000
Documentación automática: http://localhost:8000/docs
"""
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Literal

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag import Motor  # noqa: E402
from agente import Lexia  # noqa: E402
import adjuntos  # noqa: E402

app = FastAPI(title="Motor RAG y agente Lexia - Código de Policía y Código de Tránsito",
              description="Búsqueda híbrida (FAISS + BM25 + glosario coloquial) sobre la Ley 1801 de 2016 y la "
                          "Ley 769 de 2002, respuesta RAG (/query) y agente con herramientas (/agente)")

# el motor solo debería recibir llamadas del backend de Node
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("URL_BACKEND", "http://localhost:3001")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

motor = Motor()
lexia = Lexia(motor)


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


class Mensaje(BaseModel):
    rol: Literal["usuario", "lexia"]
    texto: str = Field(..., min_length=1, max_length=20000)


class Conversacion(BaseModel):
    mensajes: list[Mensaje] = Field(..., min_length=1, max_length=30,
                                    description="Historial del chat; el último mensaje es la pregunta del usuario")


@app.post("/agente")
def agente(c: Conversacion):
    """Agente Lexia: decide qué buscar, lee artículos, calcula multas y arma casos.
    Responde como Server-Sent Events (text/event-stream), un JSON por evento: estado, fuentes, respuesta, fin."""
    def eventos():
        try:
            for e in lexia.conversar([m.model_dump() for m in c.mensajes]):
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
        except Exception as e:  # clave inválida, límite del proveedor, etc.
            error = {"tipo": "error", "texto": f"Error llamando al modelo de IA: {e}"}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/adjunto")
async def adjunto(archivo: UploadFile = File(...)):
    """Convierte un archivo adjunto (imagen, PDF, Word, texto) en texto para Lexia. No se guarda en disco."""
    datos = await archivo.read()
    if len(datos) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo no puede pasar de 15 MB.")
    return adjuntos.procesar(archivo.filename, archivo.content_type, datos, motor.cliente_llm)

