"""Paso 3 (avance de la fase 2): estadísticas del corpus con spaCy.

Uso:
    python src/estadisticas.py
Genera data/procesado/estadisticas.md y estadisticas.json
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

import spacy

BASE = Path(__file__).resolve().parents[1]
CORPUS = BASE / "data" / "procesado" / "corpus.json"
SALIDA_MD = BASE / "data" / "procesado" / "estadisticas.md"
SALIDA_JSON = BASE / "data" / "procesado" / "estadisticas.json"
GLOSARIO = BASE / "data" / "glosario.json"
TERMINOS_KWIC = ["multa", "comparendo", "medida correctiva", "espacio público"]


def colocaciones_pmi(unigramas, bigramas, minimo=5, top=20):
    """Colocaciones por información mutua puntual: PMI = log2( P(a,b) / (P(a) P(b)) ).
    Solo se consideran bigramas con frecuencia >= minimo para no premiar combinaciones raras."""
    n_uni, n_bi = sum(unigramas.values()), sum(bigramas.values())
    filas = []
    for (a, b), f in bigramas.items():
        if f < minimo:
            continue
        pmi = math.log2((f / n_bi) / ((unigramas[a] / n_uni) * (unigramas[b] / n_uni)))
        filas.append((f"{a} {b}", round(pmi, 2), f))
    return sorted(filas, key=lambda x: -x[1])[:top]


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

    tokens, lemas, pos, ents, bigramas, trigramas = [], Counter(), Counter(), Counter(), Counter(), Counter()
    for doc in nlp.pipe(textos, batch_size=20):
        palabras = [t for t in doc if t.is_alpha]
        tokens.extend(t.lower_ for t in palabras)
        pos.update(t.pos_ for t in palabras)
        utiles = [t.lemma_.lower() for t in palabras if not t.is_stop and len(t) > 2]
        lemas.update(utiles)
        bigramas.update(zip(utiles, utiles[1:]))
        trigramas.update(zip(utiles, utiles[1:], utiles[2:]))
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
        "top_trigramas": [(" ".join(t), c) for t, c in trigramas.most_common(20)],
        "colocaciones_pmi": colocaciones_pmi(lemas, bigramas),
        "pos": pos.most_common(),
        "entidades": [(f"{t} [{l}]", c) for (t, l), c in ents.most_common(30)],
        "montos_y_multas": montos.most_common(15),
        "plazos": plazos.most_common(15),
        "vigencia": Counter(a["vigencia"] for a in articulos).most_common(),
    }
    # frecuencia de los términos del glosario en el corpus (texto en minúsculas)
    todo = " ".join(textos).lower()
    glosario = json.loads(GLOSARIO.read_text(encoding="utf-8"))["terminos"] if GLOSARIO.exists() else []
    stats["glosario"] = [(f"{g['termino']} (Art. {g['articulo']})", todo.count(g["termino"].lower()))
                         for g in glosario]
    stats["longitud_fragmentos"] = {
        "articulo_min": min(len(a["texto"].split()) for a in articulos),
        "articulo_max": max(len(a["texto"].split()) for a in articulos),
        "numeral_promedio": round(sum(len(n["texto"].split()) for a in articulos for n in a["numerales"])
                                  / max(1, stats["numerales"]), 1),
        "paragrafo_promedio": round(sum(len(p["texto"].split()) for a in articulos for p in a["paragrafos"])
                                    / max(1, stats["paragrafos"]), 1),
    }
    SALIDA_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Estadísticas del corpus Ley 1801 de 2016\n",
          "| Medida | Valor |", "|---|---|"]
    for k in ("articulos", "tokens", "tipos", "relacion_tipo_token",
              "palabras_promedio_por_articulo", "paragrafos", "numerales"):
        md.append(f"| {k.replace('_', ' ')} | {stats[k]} |")
    secciones = [("Lemas más frecuentes (sin stopwords)", "top_lemas"),
                 ("Bigramas más frecuentes", "top_bigramas"),
                 ("Trigramas más frecuentes", "top_trigramas"),
                 ("Etiquetas gramaticales (POS)", "pos"),
                 ("Entidades reconocidas por spaCy", "entidades"),
                 ("Montos y tipos de multa", "montos_y_multas"),
                 ("Plazos", "plazos"),
                 ("Estado de vigencia", "vigencia")]
    for titulo, clave in secciones:
        md += [f"\n## {titulo}\n", "| Término | Frecuencia |", "|---|---|"]
        md += [f"| {t} | {c} |" for t, c in stats[clave]]
    md += ["\n## Colocaciones (PMI, frecuencia >= 5)\n", "| Colocación | PMI | Frecuencia |", "|---|---|---|"]
    md += [f"| {c} | {p} | {f} |" for c, p, f in stats["colocaciones_pmi"]]
    md += ["\n## Longitud de los fragmentos (palabras)\n", "| Medida | Valor |", "|---|---|"]
    md += [f"| {k.replace('_', ' ')} | {v} |" for k, v in stats["longitud_fragmentos"].items()]
    if stats["glosario"]:
        md += ["\n## Frecuencia de los términos del glosario\n", "| Término | Apariciones |", "|---|---|"]
        md += [f"| {t} | {c} |" for t, c in stats["glosario"]]
    md.append("\n## Concordancias (KWIC)\n")
    for termino in TERMINOS_KWIC:
        md += [f"\n**{termino}**\n", "| Izquierda | Término | Derecha |", "|---:|:---:|:---|"]
        md += [f"| {i} | {t} | {d} |" for i, t, d in kwic(textos, termino)]
    SALIDA_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"Artículos: {stats['articulos']} | tokens: {n_tokens:,} | tipos: {n_tipos:,} | TTR: {stats['relacion_tipo_token']}")
    print(f"Reporte en {SALIDA_MD}")


if __name__ == "__main__":
    main()
