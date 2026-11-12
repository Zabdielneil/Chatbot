"""Paso 4 (Fase 3): parte el corpus en fragmentos, genera los embeddings y construye el índice FAISS.

Uso:
    python src/indexar.py                          # estrategia estructural (por defecto)
    python src/indexar.py --estrategia fija        # ventanas de tamaño fijo con solapamiento
    python src/indexar.py --estrategia todas       # construye las dos para compararlas

Entrada:  data/procesado/corpus.json
Salidas:  data/indice/<estrategia>.faiss  y  data/indice/<estrategia>_fragmentos.json
"""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
CORPUS = BASE / "data" / "procesado" / "corpus.json"
DIR_INDICE = BASE / "data" / "indice"

MODELO_POR_DEFECTO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# estrategia "fija": tamaño de ventana y solapamiento en palabras
VENTANA = 120
SOLAPE = 30


def cabecera(art):
    """Texto corto que se antepone a cada fragmento para que el embedding sepa de qué artículo viene."""
    epi = f". {art['epigrafe']}" if art.get("epigrafe") else ""
    return f"Artículo {art['articulo']}{epi}."


def base_fragmento(art):
    return {
        "articulo": art["articulo"],
        "epigrafe": art.get("epigrafe", ""),
        "libro": art.get("libro"),
        "titulo": art.get("titulo"),
        "capitulo": art.get("capitulo"),
        "capitulo_nombre": art.get("capitulo_nombre", ""),
        "vigencia": art.get("vigencia", "vigente"),
        "temas": art.get("temas", []),
    }


def fragmentos_estructurales(articulos):
    """Un fragmento por inciso, por numeral y por parágrafo.
    Si el artículo es corto (sin numerales ni parágrafos) queda como un solo fragmento."""
    frags = []
    for art in articulos:
        cab = cabecera(art)
        inciso = art.get("inciso") or art.get("texto", "")
        numerales = art.get("numerales", [])
        paragrafos = art.get("paragrafos", [])

        if not numerales and not paragrafos:
            frags.append({**base_fragmento(art), "tipo": "articulo",
                          "ref": f"Artículo {art['articulo']}",
                          "texto": art.get("texto", "")})
            continue

        if inciso:
            frags.append({**base_fragmento(art), "tipo": "inciso",
                          "ref": f"Artículo {art['articulo']}", "texto": inciso})
        # a cada numeral le pegamos el inicio del inciso para que no pierda el contexto
        # (ej. "Los siguientes comportamientos afectan... : 4. Orinar en la vía pública")
        intro = " ".join(inciso.split()[:40])
        for n in numerales:
            frags.append({**base_fragmento(art), "tipo": "numeral",
                          "ref": f"Artículo {art['articulo']}, numeral {n['numeral']}",
                          "texto": n["texto"], "contexto": intro})
        for p in paragrafos:
            frags.append({**base_fragmento(art), "tipo": "paragrafo",
                          "ref": f"Artículo {art['articulo']}, parágrafo {p['paragrafo']}",
                          "texto": p["texto"]})

    for f in frags:
        ctx = f" {f['contexto']} ..." if f.get("contexto") else ""
        f["texto_embedding"] = f"{cabecera(f)}{ctx} {f['texto']}".strip()
    return frags


def fragmentos_fijos(articulos, ventana=VENTANA, solape=SOLAPE):
    """Ventanas de `ventana` palabras con `solape` palabras repetidas, sin cruzar artículos."""
    frags = []
    paso = ventana - solape
    for art in articulos:
        palabras = art.get("texto", "").split()
        if not palabras:
            continue
        for i, ini in enumerate(range(0, max(len(palabras) - solape, 1), paso)):
            trozo = " ".join(palabras[ini:ini + ventana])
            frags.append({**base_fragmento(art), "tipo": "ventana",
                          "ref": f"Artículo {art['articulo']} (fragmento {i + 1})",
                          "texto": trozo})
    for f in frags:
        f["texto_embedding"] = f"{cabecera(f)} {f['texto']}"
    return frags


ESTRATEGIAS = {"estructural": fragmentos_estructurales, "fija": fragmentos_fijos}


def cargar_modelo(nombre):
    from sentence_transformers import SentenceTransformer
    print(f"Cargando modelo de embeddings: {nombre} (la primera vez se descarga, ~470 MB)")
    return SentenceTransformer(nombre)


def construir(estrategia, articulos, modelo, nombre_modelo):
    import faiss

    frags = ESTRATEGIAS[estrategia](articulos)
    for i, f in enumerate(frags):
        f["id"] = i
    print(f"\n[{estrategia}] {len(frags)} fragmentos. Generando embeddings...")
    t0 = time.time()
    vectores = modelo.encode([f["texto_embedding"] for f in frags], batch_size=32,
                             show_progress_bar=True, normalize_embeddings=True)
    vectores = np.asarray(vectores, dtype="float32")

    # vectores normalizados + producto interno = similitud coseno
    indice = faiss.IndexFlatIP(vectores.shape[1])
    indice.add(vectores)

    DIR_INDICE.mkdir(parents=True, exist_ok=True)
    faiss.write_index(indice, str(DIR_INDICE / f"{estrategia}.faiss"))
    meta = {
        "estrategia": estrategia,
        "modelo_embeddings": nombre_modelo,
        "dimension": int(vectores.shape[1]),
        "total_fragmentos": len(frags),
        "parametros": {"ventana": VENTANA, "solape": SOLAPE} if estrategia == "fija" else {},
        "fragmentos": frags,
    }
    (DIR_INDICE / f"{estrategia}_fragmentos.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    largos = [len(f["texto_embedding"].split()) for f in frags]
    print(f"[{estrategia}] índice listo: {indice.ntotal} vectores de {vectores.shape[1]} dimensiones "
          f"en {time.time() - t0:.1f} s")
    print(f"[{estrategia}] palabras por fragmento: promedio {sum(largos) / len(largos):.0f}, "
          f"máximo {max(largos)}")
    largos_128 = sum(1 for n in largos if n > 100)
    if largos_128:
        print(f"[{estrategia}] ojo: {largos_128} fragmentos pasan de ~100 palabras y el modelo "
              f"puede cortarlos (límite de 128 tokens)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estrategia", choices=[*ESTRATEGIAS, "todas"], default="estructural")
    ap.add_argument("--modelo", default=os.getenv("EMBEDDINGS_MODELO", MODELO_POR_DEFECTO))
    args = ap.parse_args()

    if not CORPUS.exists():
        raise SystemExit(f"No existe {CORPUS}. Primero corran extraer_texto.py y segmentar.py")
    articulos = json.loads(CORPUS.read_text(encoding="utf-8"))["articulos"]
    print(f"Corpus: {len(articulos)} artículos")

    modelo = cargar_modelo(args.modelo)
    estrategias = list(ESTRATEGIAS) if args.estrategia == "todas" else [args.estrategia]
    for e in estrategias:
        construir(e, articulos, modelo, args.modelo)
    print(f"\nÍndices guardados en {DIR_INDICE}")


if __name__ == "__main__":
    main()
