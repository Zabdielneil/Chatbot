"""Paso 5 (Fase 4): búsqueda semántica en FAISS + respuesta del modelo de IA (RAG).

Uso desde la terminal (para probar sin levantar la API):
    python src/rag.py "¿Cuánto es la multa por orinar en la calle?"
    python src/rag.py "¿Qué es un comparendo?" --solo-buscar
    python src/rag.py "¿Qué pasa si no recojo el popó del perro?" --k 8 --estrategia fija
"""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
DIR_INDICE = BASE / "data" / "indice"
load_dotenv(BASE.parent / ".env")  # el .env vive en la raíz del repo

NO_ENCONTRADO = ("No encontré esa información en el Código Nacional de Seguridad y Convivencia "
                 "Ciudadana (Ley 1801 de 2016).")

PROMPT_SISTEMA = f"""Eres un asistente informativo sobre el Código Nacional de Seguridad y Convivencia \
Ciudadana de Colombia (Ley 1801 de 2016, "Código de Policía").

Reglas obligatorias:
1. Responde ÚNICAMENTE con la información del CONTEXTO que te entrego. No uses conocimiento propio.
2. Cita siempre el artículo, numeral o parágrafo que sustenta cada afirmación, con el formato \
(Art. 140, num. 4) o (Art. 180, par. 1).
3. Si el CONTEXTO no permite responder la pregunta, responde exactamente: "{NO_ENCONTRADO}" \
y no agregues nada inventado.
4. Si un fragmento tiene vigencia distinta de "vigente", adviértelo en la respuesta.
5. Responde en español claro y sencillo, máximo 2 párrafos cortos, pensando en un ciudadano sin \
formación jurídica.
6. No des asesoría jurídica personalizada; si te la piden, aclara que eres una herramienta informativa."""


class Motor:
    def __init__(self, estrategia=None):
        import faiss

        self.estrategia = estrategia or os.getenv("ESTRATEGIA", "estructural")
        ruta_indice = DIR_INDICE / f"{self.estrategia}.faiss"
        ruta_meta = DIR_INDICE / f"{self.estrategia}_fragmentos.json"
        if not ruta_indice.exists():
            raise SystemExit(f"No existe {ruta_indice}. Corran primero: python src/indexar.py")
        self.indice = faiss.read_index(str(ruta_indice))
        meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
        self.fragmentos = meta["fragmentos"]
        self.nombre_modelo = meta["modelo_embeddings"]

        from sentence_transformers import SentenceTransformer
        self.modelo = SentenceTransformer(self.nombre_modelo)

        self.cliente_llm = None
        self.modelo_llm = os.getenv("LLM_MODELO", "")
        if os.getenv("LLM_API_KEY"):
            from openai import OpenAI
            # funciona con OpenAI, Groq o Gemini cambiando LLM_BASE_URL en el .env
            self.cliente_llm = OpenAI(api_key=os.getenv("LLM_API_KEY"),
                                      base_url=os.getenv("LLM_BASE_URL") or None)

    # ---------- recuperación ----------
    def buscar(self, pregunta, k=5):
        vec = self.modelo.encode([pregunta], normalize_embeddings=True)
        vec = np.asarray(vec, dtype="float32")
        puntajes, ids = self.indice.search(vec, k)
        resultados = []
        for puntaje, i in zip(puntajes[0], ids[0]):
            if i < 0:
                continue
            f = self.fragmentos[i]
            resultados.append({
                "ref": f["ref"],
                "articulo": f["articulo"],
                "epigrafe": f["epigrafe"],
                "texto": f["texto"],
                "vigencia": f["vigencia"],
                "puntaje": round(float(puntaje), 4),
            })
        return resultados

    # ---------- generación ----------
    @staticmethod
    def armar_contexto(fragmentos):
        bloques = []
        for i, f in enumerate(fragmentos, 1):
            bloques.append(f"[{i}] {f['ref']} — {f['epigrafe']} (vigencia: {f['vigencia']})\n{f['texto']}")
        return "\n\n".join(bloques)

    def preguntar(self, pregunta, k=5):
        t0 = time.time()
        fuentes = self.buscar(pregunta, k)

        if self.cliente_llm is None:
            respuesta = ("(Modo sin modelo de IA: falta LLM_API_KEY en el .env. "
                         "Estos son los fragmentos más relevantes que encontró FAISS.)")
        else:
            mensajes = [
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": f"CONTEXTO:\n{self.armar_contexto(fuentes)}\n\n"
                                            f"PREGUNTA: {pregunta}"},
            ]
            r = self.cliente_llm.chat.completions.create(
                                model=self.modelo_llm, messages=mensajes, temperature=0.1, max_tokens=2000)
            respuesta = r.choices[0].message.content.strip()

        return {
            "pregunta": pregunta,
            "respuesta": respuesta,
            "fuentes": fuentes,
            "estrategia": self.estrategia,
            "modelo_embeddings": self.nombre_modelo,
            "modelo_llm": self.modelo_llm if self.cliente_llm else None,
            "tiempo_ms": int((time.time() - t0) * 1000),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pregunta")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--estrategia", default=None)
    ap.add_argument("--solo-buscar", action="store_true", help="solo FAISS, sin llamar al modelo de IA")
    args = ap.parse_args()

    motor = Motor(args.estrategia)
    if args.solo_buscar:
        for f in motor.buscar(args.pregunta, args.k):
            print(f"{f['puntaje']:.3f}  {f['ref']} — {f['epigrafe']}\n        {f['texto'][:160]}...")
        return
    r = motor.preguntar(args.pregunta, args.k)
    print("\nRESPUESTA:\n" + r["respuesta"])
    print("\nFUENTES:")
    for f in r["fuentes"]:
        print(f"  {f['puntaje']:.3f}  {f['ref']} — {f['epigrafe']}")
    print(f"\n{r['tiempo_ms']} ms")


if __name__ == "__main__":
    main()
