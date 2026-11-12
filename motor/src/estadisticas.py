"""Paso 3 (avance de la fase 2): estadísticas del corpus con spaCy.

Uso:
    python src/estadisticas.py
Genera data/procesado/estadisticas.md y estadisticas.json
"""
import json
import re
from collections import Counter
from pathlib import Path

import spacy

BASE = Path(__file__).resolve().parents[1]
CORPUS = BASE / "data" / "procesado" / "corpus.json"
SALIDA_MD = BASE / "data" / "procesado" / "estadisticas.md"
SALIDA_JSON = BASE / "data" / "procesado" / "estadisticas.json"
TERMINOS_KWIC = ["multa", "comparendo", "medida correctiva", "espacio público"]


def cargar_modelo():
    for nombre in ("es_core_news_md", "es_core_news_sm"):
        try:
            return spacy.load(nombre)
        except OSError:
            continue
    raise SystemExit("Instalen el modelo: python -m spacy download es_core_news_md")


def kwic(textos, termino, ventana=6, maximo=8):
    filas = []
    for t in textos:
        palabras = t.split()
        bajo = [p.lower().strip(".,;:()") for p in palabras]
        n = len(termino.split())
        for i in range(len(bajo) - n + 1):
            if " ".join(bajo[i:i + n]) == termino:
                izq = " ".join(palabras[max(0, i - ventana):i])
                der = " ".join(palabras[i + n:i + n + ventana])
                filas.append((izq, " ".join(palabras[i:i + n]), der))
                if len(filas) >= maximo:
                    return filas
    return filas


def main():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    articulos = corpus["articulos"]
    textos = [f"{a['epigrafe']}. {a['texto']}" for a in articulos]
    nlp = cargar_modelo()

    tokens, lemas, pos, ents, bigramas = [], Counter(), Counter(), Counter(), Counter()
    for doc in nlp.pipe(textos, batch_size=20):
        palabras = [t for t in doc if t.is_alpha]
        tokens.extend(t.lower_ for t in palabras)
        pos.update(t.pos_ for t in palabras)
        utiles = [t.lemma_.lower() for t in palabras if not t.is_stop and len(t) > 2]
        lemas.update(utiles)
        bigramas.update(zip(utiles, utiles[1:]))
        ents.update((e.text, e.label_) for e in doc.ents)

    montos = Counter(m.lower() for t in textos for m in re.findall(
        r"multa (?:general|especial) tipo \d|\d+ salarios mínimos[^,.;]*", t, re.IGNORECASE))
    plazos = Counter(m.lower() for t in textos for m in re.findall(
        r"\b\d+ \(?\w*\)? ?(?:días|horas|meses|años)(?: hábiles| calendario)?", t))

    n_tokens, n_tipos = len(tokens), len(set(tokens))
    stats = {
        "articulos": len(articulos),
        "tokens": n_tokens,
        "tipos": n_tipos,
        "relacion_tipo_token": round(n_tipos / n_tokens, 4) if n_tokens else 0,
        "palabras_promedio_por_articulo": round(n_tokens / len(articulos), 1) if articulos else 0,
        "paragrafos": sum(len(a["paragrafos"]) for a in articulos),
        "numerales": sum(len(a["numerales"]) for a in articulos),
        "top_lemas": lemas.most_common(30),
        "top_bigramas": [(" ".join(b), c) for b, c in bigramas.most_common(20)],
        "pos": pos.most_common(),
        "entidades": [(f"{t} [{l}]", c) for (t, l), c in ents.most_common(30)],
        "montos_y_multas": montos.most_common(15),
        "plazos": plazos.most_common(15),
        "vigencia": Counter(a["vigencia"] for a in articulos).most_common(),
    }
    SALIDA_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Estadísticas del corpus Ley 1801 de 2016\n",
          "| Medida | Valor |", "|---|---|"]
    for k in ("articulos", "tokens", "tipos", "relacion_tipo_token",
              "palabras_promedio_por_articulo", "paragrafos", "numerales"):
        md.append(f"| {k.replace('_', ' ')} | {stats[k]} |")
    secciones = [("Lemas más frecuentes (sin stopwords)", "top_lemas"),
                 ("Bigramas más frecuentes", "top_bigramas"),
                 ("Etiquetas gramaticales (POS)", "pos"),
                 ("Entidades reconocidas por spaCy", "entidades"),
                 ("Montos y tipos de multa", "montos_y_multas"),
                 ("Plazos", "plazos"),
                 ("Estado de vigencia", "vigencia")]
    for titulo, clave in secciones:
        md += [f"\n## {titulo}\n", "| Término | Frecuencia |", "|---|---|"]
        md += [f"| {t} | {c} |" for t, c in stats[clave]]
    md.append("\n## Concordancias (KWIC)\n")
    for termino in TERMINOS_KWIC:
        md += [f"\n**{termino}**\n", "| Izquierda | Término | Derecha |", "|---:|:---:|:---|"]
        md += [f"| {i} | {t} | {d} |" for i, t, d in kwic(textos, termino)]
    SALIDA_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"Artículos: {stats['articulos']} | tokens: {n_tokens:,} | tipos: {n_tipos:,} | TTR: {stats['relacion_tipo_token']}")
    print(f"Reporte en {SALIDA_MD}")


if __name__ == "__main__":
    main()
