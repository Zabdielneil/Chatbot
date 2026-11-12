"""Paso 5 (Fase 4): búsqueda híbrida (FAISS + BM25) + respuesta del modelo de IA (RAG).

Uso desde la terminal (para probar sin levantar la API):
    python src/rag.py "¿Cuánto es la multa por orinar en la calle?"
    python src/rag.py "¿Qué es un comparendo?" --solo-buscar
    python src/rag.py "¿Qué pasa si no recojo el popó del perro?" --modo semantico
    python src/rag.py "..." --k 10 --estrategia fija

Modos de búsqueda:
    hibrido   (por defecto) FAISS + BM25 combinados con Reciprocal Rank Fusion
    semantico solo FAISS (embeddings)
    lexico    solo BM25 (palabras clave)
"""
import argparse
import json
import os
import re
import time
import unicodedata
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
3. Los ciudadanos usan palabras coloquiales: "orinar en la calle" equivale a "necesidades \
fisiológicas en el espacio público", "parte" a "comparendo", "pelea" a "riña". Si el CONTEXTO \
trata el mismo hecho con lenguaje jurídico, úsalo para responder.
4. Si el CONTEXTO responde la pregunta solo en parte, responde lo que sí está (con su cita) y \
aclara qué parte no aparece. Por ejemplo, si el contexto dice qué tipo de multa aplica pero no su \
valor, di el tipo de multa. El Artículo 180 define el valor de cada tipo de multa general.
5. Solo si el CONTEXTO no tiene NADA relacionado con la pregunta, responde exactamente: \
"{NO_ENCONTRADO}" y no agregues nada inventado.
6. Si un fragmento tiene vigencia distinta de "vigente", adviértelo en la respuesta.
7. Responde en español claro y sencillo, máximo 2 párrafos cortos, pensando en un ciudadano sin \
formación jurídica.
8. No des asesoría jurídica personalizada; si te la piden, aclara que eres una herramienta informativa."""

ARTICULO_MULTAS = 180  # define el valor de las multas generales tipo 1 a 4

# Glosario de expresiones coloquiales → términos de la ley (expansión de consultas).
# Amplíenlo con el análisis de la Fase 2 (frecuencias, KWIC).
SINONIMOS = {
    "orinar": "necesidades fisiológicas espacio público",
    "orine": "necesidades fisiológicas espacio público",
    "defecar": "necesidades fisiológicas espacio público",
    "popo": "excrementos animales caninos",
    "calle": "espacio público vía pública",
    "anden": "espacio público",
    "me pusieron un parte": "orden de comparendo",
    "un parte": "orden de comparendo",
    "comparendo": "orden de comparendo",
    "pelea": "riña",
    "pelear": "riña",
    "golpes": "riña agresión",
    "perro": "caninos animales",
    "perros": "caninos animales",
    "mascota": "animales domésticos",
    "trago": "bebidas alcohólicas",
    "borracho": "bebidas alcohólicas embriaguez",
    "cerveza": "bebidas alcohólicas",
    "alcohol": "bebidas alcohólicas",
    "marihuana": "sustancias psicoactivas",
    "droga": "sustancias psicoactivas",
    "drogas": "sustancias psicoactivas",
    "bareta": "sustancias psicoactivas",
    "musica": "ruido sonidos",
    "bulla": "ruido",
    "basura": "residuos sólidos",
    "grafiti": "grafitis",
    "entrar a mi casa": "ingreso a inmueble domicilio",
    "allanar": "ingreso a inmueble",
    "requisa": "registro a persona",
    "requisar": "registro a persona",
    "me llevaron": "traslado por protección",
    "ucj": "traslado por protección",
    "vendedor ambulante": "ocupación indebida del espacio público",
    "vender en la calle": "ocupación indebida del espacio público",
    "protesta": "reunión movilización",
    "marcha": "reunión movilización",
    "cuchillo": "armas elementos cortantes",
    "navaja": "armas elementos cortantes",
    "colarse": "transporte público",
    "no pago": "no pago de multas",
}

STOPWORDS = set("""a al algo ante con contra cual cuando de del desde donde e el ella ellas ellos en
entre era es esa ese eso esta este esto la las le les lo los mas me mi mis muy ni no nos o os para pero
por porque que quien se si sin sobre su sus te tu un una uno unos unas y ya hay como cuanto cuanta
puedo puede pueden debo hacer pasa""".split())


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())  # NFKD también separa ligaduras (ﬁ → fi)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def tokenizar(texto):
    return [t for t in re.findall(r"\w+", normalizar(texto)) if len(t) > 2 and t not in STOPWORDS]


def expandir_consulta(pregunta):
    """Agrega a la pregunta los términos jurídicos equivalentes a las expresiones coloquiales."""
    base = normalizar(pregunta)
    extras = list(dict.fromkeys(
        v for k, v in SINONIMOS.items() if re.search(rf"\b{re.escape(normalizar(k))}\b", base)))
    return f"{pregunta} {' '.join(extras)}".strip(), extras


class Motor:
    def __init__(self, estrategia=None):
        import faiss
        from rank_bm25 import BM25Okapi

        self.estrategia = estrategia or os.getenv("ESTRATEGIA", "estructural")
        ruta_indice = DIR_INDICE / f"{self.estrategia}.faiss"
        ruta_meta = DIR_INDICE / f"{self.estrategia}_fragmentos.json"
        if not ruta_indice.exists():
            raise SystemExit(f"No existe {ruta_indice}. Corran primero: python src/indexar.py")
        self.indice = faiss.read_index(str(ruta_indice))
        meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
        self.fragmentos = meta["fragmentos"]
        self.nombre_modelo = meta["modelo_embeddings"]

        # índice léxico BM25 sobre los mismos fragmentos
        self.bm25 = BM25Okapi([tokenizar(f["texto_embedding"]) for f in self.fragmentos])

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
    def _semantico(self, consulta, n):
        vec = np.asarray(self.modelo.encode([consulta], normalize_embeddings=True), dtype="float32")
        puntajes, ids = self.indice.search(vec, n)
        return [(int(i), float(p)) for p, i in zip(puntajes[0], ids[0]) if i >= 0]

    def _lexico(self, consulta, n):
        puntajes = self.bm25.get_scores(tokenizar(consulta))
        ids = np.argsort(puntajes)[::-1][:n]
        return [(int(i), float(puntajes[i])) for i in ids if puntajes[i] > 0]

    def _relacionados(self, frag):
        """Si se recuperó un numeral, trae los parágrafos del mismo artículo que lo mencionan
        (ahí suele estar la tabla de multas: 'Numeral 11 — Multa general tipo 1')."""
        m = re.search(r"numeral (\d+)", frag["ref"])
        if not m:
            return []
        n = m.group(1)
        patron = re.compile(rf"numeral(?:es)?\b[^.]{{0,80}}\b{n}\b", re.IGNORECASE)
        return [i for i, f in enumerate(self.fragmentos)
                if f["articulo"] == frag["articulo"] and f["tipo"] == "paragrafo" and patron.search(f["texto"])]

    def _numerales_del_paragrafo(self, frag, puntajes_bm25):
        """Si se recuperó un parágrafo (p. ej. la tabla de multas), trae los numerales del mismo
        artículo que más se parecen a la pregunta, para que la IA sepa qué comportamiento es cuál."""
        if frag["tipo"] != "paragrafo":
            return []
        hermanos = [i for i, f in enumerate(self.fragmentos)
                    if f["articulo"] == frag["articulo"] and f["tipo"] == "numeral" and puntajes_bm25[i] > 0]
        hermanos.sort(key=lambda i: puntajes_bm25[i], reverse=True)
        return hermanos[:2]

    def _medida_de_numeral(self, frag):
        """Busca en la tabla del parágrafo del mismo artículo la fila de este numeral.
        Ej.: Art. 140, numeral 11 → 'Multa General tipo 4; Participación en programa comunitario...'"""
        m = re.search(r"numeral (\d+)", frag["ref"])
        if not m:
            return None
        n = m.group(1)
        fila = re.compile(rf"\bNumeral\s+{n}\b\s*(.+?)(?=\bNumeral\s+\d+\b|\(Par[áa]grafo|$)", re.IGNORECASE)
        for f in self.fragmentos:
            if f["articulo"] == frag["articulo"] and f["tipo"] == "paragrafo":
                encontrado = fila.search(f["texto"])
                if encontrado and re.search(r"multa|medida|suspensi|destrucci|remoci|participaci|amonestaci",
                                            encontrado.group(1), re.IGNORECASE):
                    return f"{encontrado.group(1).strip()} ({f['ref'].replace('Artículo', 'Art.')})"
        return None

    def buscar(self, pregunta, k=8, modo="hibrido"):
        consulta, extras = expandir_consulta(pregunta)
        candidatos = 40
        puntajes_bm25 = self.bm25.get_scores(tokenizar(consulta))

        if modo == "semantico":
            ranking = self._semantico(consulta, k)
        elif modo == "lexico":
            ranking = self._lexico(consulta, k)
        else:
            # Reciprocal Rank Fusion: premia lo que sale arriba en cualquiera de las dos listas
            rrf = {}
            for lista in (self._semantico(consulta, candidatos), self._lexico(consulta, candidatos)):
                for pos, (i, _) in enumerate(lista):
                    rrf[i] = rrf.get(i, 0) + 1 / (60 + pos)
            ranking = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:k]

        vistos, resultados = set(), []

        def agregar(i, puntaje, origen):
            if i in vistos:
                return
            vistos.add(i)
            f = self.fragmentos[i]
            resultados.append({
                "ref": f["ref"], "articulo": f["articulo"], "epigrafe": f["epigrafe"],
                "texto": f["texto"], "vigencia": f["vigencia"],
                "medida_correctiva": self._medida_de_numeral(f),
                "puntaje": round(puntaje, 4), "origen": origen,
            })

        for i, puntaje in ranking:
            agregar(i, puntaje, modo)
            for j in self._relacionados(self.fragmentos[i]) + \
                     self._numerales_del_paragrafo(self.fragmentos[i], puntajes_bm25):
                agregar(j, 0.0, "relacionado")

        # si alguna fuente menciona "multa general tipo X", se agrega el Art. 180 que define su valor
        if any(re.search(r"multa general tipo", normalizar(r["texto"])) for r in resultados):
            for j, f in enumerate(self.fragmentos):
                if f["articulo"] == ARTICULO_MULTAS and f["tipo"] in ("inciso", "numeral", "articulo"):
                    agregar(j, 0.0, "relacionado")
        self.ultima_expansion = extras
        return resultados

    # ---------- generación ----------
    @staticmethod
    def armar_contexto(fragmentos):
        bloques = []
        for i, f in enumerate(fragmentos, 1):
            bloque = f"[{i}] {f['ref']} — {f['epigrafe']} (vigencia: {f['vigencia']})\n{f['texto']}"
            if f.get("medida_correctiva"):
                bloque += f"\nMEDIDA CORRECTIVA PARA ESTE NUMERAL: {f['medida_correctiva']}"
            bloques.append(bloque)
        return "\n\n".join(bloques)

    def preguntar(self, pregunta, k=8, modo="hibrido"):
        t0 = time.time()
        fuentes = self.buscar(pregunta, k, modo)

        if self.cliente_llm is None:
            respuesta = ("(Modo sin modelo de IA: falta LLM_API_KEY en el .env. "
                         "Estos son los fragmentos más relevantes que se encontraron.)")
        else:
            mensajes = [
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": f"CONTEXTO:\n{self.armar_contexto(fuentes)}\n\n"
                                            f"PREGUNTA: {pregunta}"},
            ]
            r = self.cliente_llm.chat.completions.create(
                model=self.modelo_llm, messages=mensajes, temperature=0.1, max_tokens=2000)
            respuesta = (r.choices[0].message.content or "").strip() or NO_ENCONTRADO
            respuesta = re.sub(r"\s*【[^】]*】", "", respuesta)  # basura de citas internas de GPT-OSS

        return {
            "pregunta": pregunta,
            "respuesta": respuesta,
            "fuentes": fuentes,
            "terminos_agregados": self.ultima_expansion,
            "modo_busqueda": modo,
            "estrategia": self.estrategia,
            "modelo_embeddings": self.nombre_modelo,
            "modelo_llm": self.modelo_llm if self.cliente_llm else None,
            "tiempo_ms": int((time.time() - t0) * 1000),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pregunta")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--estrategia", default=None)
    ap.add_argument("--modo", choices=["hibrido", "semantico", "lexico"], default="hibrido")
    ap.add_argument("--solo-buscar", action="store_true", help="solo recuperación, sin llamar al modelo de IA")
    args = ap.parse_args()

    motor = Motor(args.estrategia)
    if args.solo_buscar:
        fuentes = motor.buscar(args.pregunta, args.k, args.modo)
        if motor.ultima_expansion:
            print(f"Consulta expandida con: {motor.ultima_expansion}\n")
        for f in fuentes:
            marca = "  ↳" if f["origen"] == "relacionado" else f"{f['puntaje']:.3f}"
            print(f"{marca:>6}  {f['ref']} — {f['epigrafe']}\n        {f['texto'][:160]}...")
        return
    r = motor.preguntar(args.pregunta, args.k, args.modo)
    if r["terminos_agregados"]:
        print(f"Consulta expandida con: {r['terminos_agregados']}")
    print("\nRESPUESTA:\n" + r["respuesta"])
    print("\nFUENTES:")
    for f in r["fuentes"]:
        marca = "  ↳" if f["origen"] == "relacionado" else f"{f['puntaje']:.3f}"
        print(f"{marca:>6}  {f['ref']} — {f['epigrafe']}")
        if f.get("medida_correctiva"):
            print(f"          medida: {f['medida_correctiva'][:110]}")
    print(f"\n{r['tiempo_ms']} ms")


if __name__ == "__main__":
    main()
