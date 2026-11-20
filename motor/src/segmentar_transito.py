"""Corpus complementario: Código Nacional de Tránsito Terrestre (Ley 769 de 2002).

Uso (desde motor/):
    python src/segmentar_transito.py data/raw/Ley_769_de_2002.pdf --fecha 2026-11-19
Salida: data/procesado/corpus_transito.json (mismo esquema que corpus.json, con "norma")

Diferencias con la Ley 1801 que maneja este script:
- Los epígrafes van en MAYÚSCULAS: "ARTÍCULO 131. MULTAS. Modificado por ..."
- Las notas de vigencia son frases sueltas ("Modificado por el art. 21, Ley 1383 de 2010. El nuevo
  texto es el siguiente:") o van entre paréntesis; se separan del texto y se guardan en notas.
- Hay artículos adicionados con letra (85A, 158A).
- El Art. 131 agrupa las infracciones por literal (A, B, C...) con códigos (A.1, B.2...); cada código
  es un "numeral" cuyo contexto es la frase del grupo con el valor de la multa.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extraer_texto import leer_pdf, limpiar  # noqa: E402
from segmentar import separar_notas, vigencia_unidad, temas_de, unir  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
SALIDA = BASE / "data" / "procesado" / "corpus_transito.json"
SALIDA_TXT = BASE / "data" / "procesado" / "ley769_limpio.txt"
NORMA = "Ley 769 de 2002"

RUIDO = re.compile(r"^(Ley 769 de 2002(\s+\d+)?|\d{1,3}|EVA - Gestor Normativo|"
                   r"Departamento Administrativo de la Funci[oó]n P[uú]blica)\s*$")
RE_ARTICULO = re.compile(r"^ART[ÍI]CULO\s+(\d{1,3})\s*([A-Z])?\s*[°ºo]?\s*\.?\s*(.*)$")
RE_TITULO = re.compile(r"^T[ÍI]TULO\s+([IVX]+)\.?\s*(.*)$")
RE_CAPITULO = re.compile(r"^CAP[ÍI]TULO\s+([IVX]+|[ÚU]NICO)\.?\s*(.*)$")
RE_PARAGRAFO = re.compile(r"^PAR[ÁA]GRAFO\s*(\d+|[ÚU]NICO|TRANSITORIO)?\s*[°ºo]?\.?\s*(.*)$", re.IGNORECASE)
RE_NUMERAL = re.compile(r"^(\d{1,2})\s*[\.\)]\s+(\S.*)$")
RE_CODIGO = re.compile(r"^([A-I])\.(\d{1,2})\.?\s+(\S.*)$")           # A.1. No transitar por la derecha
RE_HISTORICO = re.compile(r"^(Texto (anterior|original)|Legislaci[oó]n anterior)", re.IGNORECASE)
RE_GRUPO = re.compile(r"^([A-I])\.\s+(Será sancionado.*)$")           # A. Será sancionado con multa ...
# notas como frase suelta dentro del texto
RE_NOTA_FRASE = re.compile(
    r"(?:(?:Inciso|Par[áa]grafo|Numeral|Literal|Art[íi]culo)\s+[\w°º]*\s*)?"
    r"(?:Modificad[oa]|Adicionad[oa]|Derogad[oa]|Subrogad[oa]|Sustituid[oa]|Corregid[oa])\s+"
    r"(?:por\s+)?(?:el\s+)?(?:art(?:ículo)?\.?\s*[\d\w]+,?\s*(?:de\s+la\s+)?)?(?:Ley|Decreto)\s+\d+\s+de\s+\d{4}\.?"
    r"(?:\s*El nuevo texto es el siguiente:)?",
    re.IGNORECASE,
)


def separar_todo(texto):
    """Notas entre paréntesis (como en la 1801) + notas en forma de frase."""
    texto, notas = separar_notas(texto)
    frases = [re.sub(r"\s+", " ", m).strip() for m in RE_NOTA_FRASE.findall(texto)]
    texto = RE_NOTA_FRASE.sub(" ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto, notas + frases


def partir(art_num, lineas):
    """Inciso, numerales (o códigos del Art. 131) y parágrafos de un artículo."""
    bloques, actual, siguiente, grupo = [], ["inciso", None, [], None], 1, None
    for linea in lineas:
        mp, mn, mc, mg = (RE_PARAGRAFO.match(linea), RE_NUMERAL.match(linea),
                          RE_CODIGO.match(linea), RE_GRUPO.match(linea))
        if mp:
            bloques.append(actual)
            actual = ["paragrafo", (mp.group(1) or "único").lower(), [mp.group(2)], None]
        elif mg:
            bloques.append(actual)
            grupo = f"{mg.group(1)}. {mg.group(2)}"
            actual = ["grupo", mg.group(1), [mg.group(2)], None]
        elif mc and grupo and mc.group(1) != grupo[0]:
            # código de un grupo cuya frase de valor no trae la fuente (pasa con el grupo E)
            grupo = f"{mc.group(1)}. (La fuente consultada no indica el valor de la multa de este grupo.)"
            bloques.append(actual)
            actual = ["numeral", f"{mc.group(1)}.{mc.group(2)}", [mc.group(3)], grupo]
        elif mc and grupo and mc.group(1) == grupo[0]:
            bloques.append(actual)
            actual = ["numeral", f"{mc.group(1)}.{mc.group(2)}", [mc.group(3)], grupo]
        elif mn and int(mn.group(1)) == siguiente and actual[0] in ("inciso", "numeral") and not grupo:
            bloques.append(actual)
            actual = ["numeral", mn.group(1), [mn.group(2)], None]
            siguiente += 1
        else:
            actual[2].append(linea)
    bloques.append(actual)

    inciso_partes, numerales, paragrafos = [], [], []
    for tipo, ident, lns, grp in bloques:
        texto, notas = separar_todo(unir(lns))
        if not texto and not notas:
            continue
        if tipo in ("inciso", "grupo"):
            inciso_partes.append((texto, notas))
            continue
        unidad = {"texto": texto, "vigencia": vigencia_unidad(notas), "notas": notas}
        if grp:  # el contexto del código es la frase del grupo, con el valor de la multa
            unidad["grupo"] = separar_todo(grp)[0][:300]
        if tipo == "numeral":
            numerales.append({"numeral": ident, **unidad})
        else:
            paragrafos.append({"paragrafo": ident, **unidad})
    inciso = " ".join(t for t, _ in inciso_partes[:1])
    notas_inciso = [n for _, ns in inciso_partes[:1] for n in ns]
    return inciso, vigencia_unidad(notas_inciso), numerales, paragrafos


def segmentar(texto):
    lineas = [l.strip() for l in texto.splitlines()]
    lineas = [l for l in lineas if l and not RUIDO.match(l) and l != "*jurisprudencia*"]
    articulos, art = [], None
    ubic = {"titulo": None, "titulo_nombre": "", "capitulo": None, "capitulo_nombre": ""}
    esperando = None
    historico = False  # después de "Texto anterior" viene la versión derogada: no se incluye

    def cerrar():
        if art is None:
            return
        cuerpo = art.pop("_lineas")
        inciso, vig_inciso, numerales, paragrafos = partir(art["articulo"], cuerpo)
        art["texto"], notas = separar_todo(unir(cuerpo))
        art["inciso"], art["inciso_vigencia"] = inciso, vig_inciso
        art["numerales"], art["paragrafos"] = numerales, paragrafos
        todas = art.pop("_notas_epigrafe") + notas
        art["notas_vigencia"] = " | ".join(todas)
        bajo = " ".join(todas).lower()
        if "derogad" in bajo and len(art["texto"].split()) < 25:
            art["vigencia"] = "derogado"
        elif re.search(r"inexequib", bajo) and not re.search(r"exequible", bajo.replace("inexequib", "")):
            art["vigencia"] = "inexequible"
        elif todas:
            art["vigencia"] = "vigente con cambios"
        else:
            art["vigencia"] = "vigente"
        art["normas_modificatorias"] = sorted(set(re.findall(r"Ley\s+\d{3,4}\s+de\s+\d{4}", " ".join(todas))))
        art["temas"] = temas_de(art)
        art["n_palabras"] = len(art["texto"].split())
        articulos.append(art)

    for linea in lineas:
        mt, mc, ma = RE_TITULO.match(linea), RE_CAPITULO.match(linea), RE_ARTICULO.match(linea)
        if mt:
            ubic.update(titulo=mt.group(1), titulo_nombre=mt.group(2).strip(". "), capitulo=None, capitulo_nombre="")
            esperando = "titulo_nombre" if not mt.group(2).strip(". ") else None
            continue
        if mc:
            ubic.update(capitulo=mc.group(1), capitulo_nombre=mc.group(2).strip(". "))
            esperando = "capitulo_nombre" if not mc.group(2).strip(". ") else None
            continue
        if esperando and not ma and len(linea) < 120:
            ubic[esperando] = linea.strip(". ")
            esperando = None
            continue
        esperando = None
        if ma:
            historico = False
            num = int(ma.group(1))
            letra = ma.group(2) or ""
            resto = ma.group(3).strip()
            # epígrafe: lo que va en mayúsculas hasta el primer punto
            m = re.match(r"^([^a-záéíóúñ]{3,}?)\.\s*(.*)$", resto)
            epigrafe, inicio = (m.group(1), m.group(2)) if m else ("", resto)
            inicio, notas_epi = separar_todo(inicio)
            cerrar()
            art = {
                "id": f"l769_art_{num}{letra}", "norma": NORMA, "articulo": f"{num}{letra}" if letra else num,
                "epigrafe": epigrafe.strip().capitalize(), "libro": None, "libro_nombre": "",
                "titulo": ubic["titulo"], "titulo_nombre": ubic["titulo_nombre"],
                "capitulo": ubic["capitulo"], "capitulo_nombre": ubic["capitulo_nombre"],
                "_lineas": [inicio] if inicio else [], "_notas_epigrafe": notas_epi,
            }
            continue
        if RE_HISTORICO.match(linea):
            historico = True
        if art is not None and not historico:
            art["_lineas"].append(linea)
    cerrar()
    return articulos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--url", default="https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5557")
    ap.add_argument("--fecha", default=date.today().isoformat())
    args = ap.parse_args()

    texto = limpiar(leer_pdf(args.pdf))
    SALIDA_TXT.write_text(texto, encoding="utf-8")
    articulos = segmentar(texto)
    # si un número aparece dos veces (error de la fuente), se conserva el primero
    vistos, unicos = set(), []
    for a in articulos:
        if a["articulo"] not in vistos:
            vistos.add(a["articulo"])
            unicos.append(a)
    corpus = {"metadatos": {
        "norma": f"{NORMA} - Código Nacional de Tránsito Terrestre",
        "fuente": "Departamento Administrativo de la Función Pública - Gestor Normativo",
        "url": args.url, "fecha_consulta": args.fecha, "total_articulos": len(unicos),
        "esquema": "titulo > capitulo > articulo > (inciso, numerales/códigos de infracción, paragrafos)",
        "justificacion": "Corpus complementario solicitado por el docente: muchas consultas ciudadanas "
                         "(multas de tránsito, comparendos, licencia) se rigen por esta ley y no por la 1801.",
    }, "articulos": unicos}
    SALIDA.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Corpus de tránsito: {len(unicos)} artículos en {SALIDA}")
    print("Vigencia:", dict(Counter(a["vigencia"] for a in unicos)))
    print("Numerales/códigos:", sum(len(a["numerales"]) for a in unicos),
          "| parágrafos:", sum(len(a["paragrafos"]) for a in unicos))
    print("Sin epígrafe:", [a["articulo"] for a in unicos if not a["epigrafe"]][:20])


if __name__ == "__main__":
    main()
