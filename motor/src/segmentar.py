"""Paso 2: segmenta el texto limpio en libro > título > capítulo > artículo > parágrafo/numeral
y genera data/procesado/corpus.json con metadatos.

Uso:
    python src/segmentar.py --fuente "Función Pública - Gestor Normativo" --url "https://..." --fecha 2026-11-12
"""
import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ENTRADA = BASE / "data" / "procesado" / "ley1801_limpio.txt"
SALIDA = BASE / "data" / "procesado" / "corpus.json"
TOTAL_ARTICULOS = 243

RE_LIBRO = re.compile(r"^LIBRO\s+(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO)\.?\s*(.*)$")
RE_TITULO = re.compile(r"^T[ÍI]TULO\s+([IVXLC]+)\.?\s*(.*)$")
RE_CAPITULO = re.compile(r"^CAP[ÍI]TULO\s+([IVXLC]+|[ÚU]NICO)\.?\s*(.*)$")
RE_ARTICULO = re.compile(
    r"^(?:ART[ÍI]CULO|Art[íi]culo)\s+(\d{1,3})\s*(?:[°ºo]\s*)?(?:\.|-|–)\s*(.*)$"
)
RE_PARAGRAFO = re.compile(
    r"^(?:PAR[ÁA]GRAFO|Par[áa]grafo)\b\s*((?:\d+\s*[°ºo]?)|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|"
    r"TRANSITORIO|[ÚU]NICO)?\s*(TRANSITORIO)?\s*[\.\-–:]?\s*(.*)$"
)
RE_NUMERAL = re.compile(r"^(\d{1,2})\s*[\.\)]\s+(\S.*)$")
RE_NOTA = re.compile(
    r"^(Notas? de Vigencia|Jurisprudencia Vigencia|Notas? del Editor|Legislaci[oó]n Anterior|"
    r"Texto original de la Ley|Concordancias|Doctrina Concordante|Resumen de Notas de Vigencia|"
    r"Jurisprudencia Concordante|<?Ver Notas)",
    re.IGNORECASE,
)

# notas de vigencia que la fuente mete dentro del texto, p. ej.
# "(Declarado INEXEQUIBLE mediante Sentencia de la Corte Constitucional C-281 de 2017)"
# "(Numeral adicionado por el Art. 2 de la Ley 2000 de 2019)"
RE_NOTA_EN_LINEA = re.compile(
    r"\((?:[^()]|\([^()]*\))*?(?:modificad|adicionad|corregid|derogad|declarad|inexequib|exequib|"
    r"subrogad|ver sentencia|inhibid)(?:[^()]|\([^()]*\))*?\)",
    re.IGNORECASE,
)
RE_MARCA_EDITORIAL = re.compile(r"\*jurisprudencia\*", re.IGNORECASE)
# las firmas de la ley no son parte del Art. 243
RE_FIN_LEY = re.compile(r"^EL PRESIDENTE DEL HONORABLE SENADO", re.IGNORECASE)
# encabezados de las tablas de medidas correctivas ("COMPORTAMIENTOS | MEDIDA CORRECTIVA A APLICAR")
RE_ENCABEZADO_TABLA = re.compile(r"^COMPOR-?TAMIENTOS|MEDIDAS? CORRECTIVAS?\s*A\s*APLICAR|^ACTIVIDADES", re.IGNORECASE)

ROMANOS_NUM = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def a_romano(n):
    r = ""
    for valor, letra in ROMANOS_NUM:
        while n >= valor:
            r, n = r + letra, n - valor
    return r


def separar_notas(texto):
    """Quita del texto las notas de vigencia entre paréntesis y las devuelve aparte."""
    notas = [re.sub(r"\s+", " ", m).strip() for m in RE_NOTA_EN_LINEA.findall(texto)]
    limpio = RE_MARCA_EDITORIAL.sub(" ", RE_NOTA_EN_LINEA.sub(" ", texto))
    return re.sub(r"\s+", " ", limpio).strip(), notas


def vigencia_unidad(notas):
    """Vigencia de un inciso, numeral o parágrafo según las notas que lo acompañan."""
    t = " ".join(notas).lower()
    if not t:
        return "vigente"
    parcial = re.search(r"subrayad|con excepci[oó]n|inciso", t)
    if "inexequib" in t:
        return "inexequible parcial" if parcial else "inexequible"
    if "condicional" in t:
        return "exequibilidad condicionada"
    if "derogad" in t:
        return "derogado"
    if re.search(r"modificad|adicionad|corregid|subrogad", t):
        return "modificado"
    return "vigente"  # declarado exequible o solo "ver sentencia"


def es_linea_mayuscula(linea):
    letras = [c for c in linea if c.isalpha()]
    return len(letras) >= 3 and sum(c.isupper() for c in letras) / len(letras) > 0.85


def detectar_estructura(lineas):
    """La edición usada no rotula los títulos con "TÍTULO X": solo pone su nombre en mayúsculas
    antes del primer capítulo o artículo. Aquí se identifican:
      - nombre del libro: el bloque de líneas seguidas en mayúsculas después de "LIBRO ..."
      - título: línea en mayúsculas cuyo siguiente renglón es un CAPÍTULO o un ARTÍCULO
      - fin: donde empiezan las firmas de la ley
    Devuelve {indice: (tipo, valor)} y el índice donde termina el articulado."""
    especiales, fin = {}, len(lineas)

    def siguiente(i):
        j = i + 1
        while j < len(lineas) and not lineas[j].strip():
            j += 1
        return j

    def anterior(i):
        j = i - 1
        while j >= 0 and not lineas[j].strip():
            j -= 1
        return j

    for i, bruta in enumerate(lineas):
        linea = bruta.strip()
        if RE_FIN_LEY.match(linea):
            fin = i
            break
        if RE_LIBRO.match(linea):
            j, nombre = siguiente(i), []
            while j < len(lineas) and lineas[j].strip() and es_linea_mayuscula(lineas[j].strip()) \
                    and not RE_CAPITULO.match(lineas[j].strip()):
                nombre.append(lineas[j].strip())
                especiales[j] = ("libro_nombre", None)
                j += 1
            especiales[i] = ("libro", " ".join(nombre))
            continue
        if i in especiales or not linea or not es_linea_mayuscula(linea):
            continue
        if re.match(r"^(LIBRO|T[ÍI]TULO|CAP[ÍI]TULO|ART[ÍI]CULO|PAR[ÁA]GRAFO)", linea, re.IGNORECASE):
            continue
        if RE_ENCABEZADO_TABLA.search(linea):
            continue
        sig, ant = siguiente(i), anterior(i)
        sig_linea = lineas[sig].strip() if sig < len(lineas) else ""
        ant_linea = lineas[ant].strip() if ant >= 0 else ""
        if RE_CAPITULO.match(ant_linea):
            continue  # es el nombre de un capítulo
        if RE_CAPITULO.match(sig_linea) or RE_ARTICULO.match(sig_linea):
            especiales[i] = ("titulo", linea.rstrip("."))
        elif es_linea_mayuscula(sig_linea) and not RE_ENCABEZADO_TABLA.search(sig_linea):
            # línea suelta entre el nombre del libro y el título (p. ej. Libro Primero): se descarta
            especiales[i] = ("omitir", linea)
    return especiales, fin


# palabras clave para etiquetar el tema de cada artículo (ajústenlas con el análisis de la fase 2)
TEMAS = {
    "espacio público": ["espacio público", "vía pública", "andén", "parque"],
    "multas": ["multa general", "multa especial", "multa tipo", "salarios mínimos diarios"],
    "medidas correctivas": ["medida correctiva", "medidas correctivas", "amonestación", "participación en programa"],
    "procedimiento": ["proceso verbal", "audiencia", "recurso de apelación", "comparendo", "descargos"],
    "autoridades de policía": ["alcalde", "inspector de policía", "corregidor", "comandante de estación", "autoridades de policía"],
    "animales": ["animal", "animales", "caninos", "mascota", "potencialmente peligros"],
    "domicilio y privacidad": ["domicilio", "ingreso a inmueble", "registro", "intimidad"],
    "sustancias y alcohol": ["sustancias psicoactivas", "bebidas alcohólicas", "consumo de"],
    "medios de policía": ["traslado por protección", "retiro del sitio", "registro a persona", "uso de la fuerza"],
    "ambiente": ["ambiente", "recursos naturales", "fauna", "flora", "ruido"],
    "convivencia y seguridad": ["riña", "armas", "seguridad de las personas", "convivencia"],
    "actividad económica": ["actividad económica", "establecimiento", "comercio"],
    "reuniones y protesta": ["reunión", "aglomeraciones", "movilización", "protesta"],
}

ROMANOS = {"PRIMERO": 1, "SEGUNDO": 2, "TERCERO": 3, "CUARTO": 4, "QUINTO": 5}


def es_mayuscula(linea):
    letras = [c for c in linea if c.isalpha()]
    return len(letras) >= 3 and sum(c.isupper() for c in letras) / len(letras) > 0.85


def unir(lineas):
    texto = " ".join(l.strip() for l in lineas if l.strip())
    return re.sub(r"\s+", " ", texto).strip()


def vigencia_de(texto, notas):
    todo = f"{texto} {notas}"
    bajo = todo.lower()
    banderas = []
    if "derogad" in bajo:
        banderas.append("derogado")
    if "inexequible" in bajo:
        banderas.append("inexequible (total o parcial)")
    if re.search(r"condicionalmente\s+exequible|exequible.{0,40}en el entendido", bajo):
        banderas.append("exequibilidad condicionada")
    if re.search(r"modificad[oa] por|subrogad", bajo):
        banderas.append("modificado")
    if re.search(r"adicionad[oa] por", bajo):
        banderas.append("adicionado")

    leyes = sorted({m for m in re.findall(r"Ley\s+\d{3,4}\s+de\s+\d{4}", todo) if "1801" not in m})
    sentencias = sorted({re.sub(r"\s+", "", s) for s in re.findall(r"C\s*-\s*\d{2,4}\s*(?:/|de)\s*\d{2,4}", todo)})

    if "derogado" in banderas and not texto.strip():
        estado = "derogado"
    elif banderas:
        estado = "vigente con cambios"
    else:
        estado = "vigente"
    return estado, banderas, leyes, sentencias


def temas_de(articulo):
    base = f"{articulo['epigrafe']} {articulo['texto']}".lower()
    encontrados = [t for t, claves in TEMAS.items() if any(c in base for c in claves)]
    return encontrados or ["general"]


RE_NOTA_LINEA_COMPLETA = re.compile(r"^\(.*\)$")
RE_NOTA_CON_UNIDAD = re.compile(
    r"^\(\s*(Numerales?|Par[áa]grafos?)\s+((?:\d+|[úu]nico|transitorio)(?:\s*(?:,|y)\s*\d+)*)", re.IGNORECASE)


def notas_finales(lineas):
    """Separa las notas que la fuente pone al final del artículo, después de su último numeral o parágrafo.
    Esas notas se refieren al artículo completo, salvo que nombren una unidad
    ("(Parágrafo 3, declarado INEXEQUIBLE...)", "(Numerales 2, 3 y 4 adicionados...)")."""
    lineas = list(lineas)
    finales = []
    while lineas and RE_NOTA_LINEA_COMPLETA.match(lineas[-1].strip()) and RE_NOTA_EN_LINEA.search(lineas[-1]):
        finales.insert(0, re.sub(r"\s+", " ", lineas.pop().strip()))
    del_articulo, por_unidad = [], []  # por_unidad: (tipo, id, nota)
    for nota in finales:
        m = RE_NOTA_CON_UNIDAD.match(nota)
        if m:
            tipo = "numeral" if m.group(1).lower().startswith("numeral") else "paragrafo"
            for ident in re.findall(r"\d+|[úu]nico|transitorio", m.group(2), re.IGNORECASE):
                por_unidad.append((tipo, ident.lower(), nota))
        else:
            del_articulo.append(nota)
    return lineas, del_articulo, por_unidad


def partir_cuerpo(lineas):
    """Separa inciso principal, numerales y parágrafos respetando los saltos de línea del PDF.
    Devuelve también las notas de vigencia que aplican al artículo completo."""
    lineas, notas_articulo, notas_unidad = notas_finales(lineas)
    bloques = []  # (tipo, id, [lineas])
    actual = ["inciso", None, []]
    siguiente_num = 1
    for linea in lineas:
        mp = RE_PARAGRAFO.match(linea)
        mn = RE_NUMERAL.match(linea)
        if mp:
            bloques.append(actual)
            ident = " ".join(x for x in (mp.group(1), mp.group(2)) if x) or "único"
            actual = ["paragrafo", ident.strip(), [mp.group(3)]]
        elif mn and int(mn.group(1)) == siguiente_num and actual[0] != "paragrafo":
            bloques.append(actual)
            actual = ["numeral", mn.group(1), [mn.group(2)]]
            siguiente_num += 1
        else:
            actual[2].append(linea)
    bloques.append(actual)

    # si todo el artículo fue declarado inexequible o derogado, lo heredan todas sus unidades
    vigencia_articulo = vigencia_unidad(notas_articulo)
    hereda = vigencia_articulo if vigencia_articulo in ("inexequible", "derogado") else None

    def unidad(clave, b):
        texto, notas = separar_notas(unir(b[2]))
        ident = (b[1] or "").split()[0].lower() if b[1] else ""
        notas += [n for tipo, i, n in notas_unidad if tipo == clave and i == ident]
        return {clave: b[1], "texto": texto, "vigencia": hereda or vigencia_unidad(notas), "notas": notas}

    inciso_texto, inciso_notas = separar_notas(unir(next((b[2] for b in bloques if b[0] == "inciso"), [])))
    inciso = {"texto": inciso_texto, "vigencia": hereda or vigencia_unidad(inciso_notas), "notas": inciso_notas}
    numerales = [unidad("numeral", b) for b in bloques if b[0] == "numeral"]
    paragrafos = [unidad("paragrafo", b) for b in bloques if b[0] == "paragrafo"]
    return inciso, numerales, paragrafos, notas_articulo, vigencia_articulo


def segmentar(texto):
    lineas = texto.splitlines()
    especiales, fin = detectar_estructura(lineas)
    titulos_en_libro = 0
    ubic = {"libro": None, "titulo": None, "capitulo": None}
    nombres = {"libro": "", "titulo": "", "capitulo": ""}
    esperando_nombre = None
    articulos = []
    art = None
    en_nota = False
    nota_historica = False
    ultimo = 0

    def cerrar():
        if art is None:
            return
        cuerpo = art.pop("_lineas")
        notas = unir(art.pop("_notas"))
        inciso, numerales, paragrafos, notas_articulo, vigencia_articulo = partir_cuerpo(cuerpo)
        art["texto"], notas_texto = separar_notas(unir(cuerpo))
        art["inciso"] = inciso["texto"]
        art["inciso_vigencia"] = inciso["vigencia"]
        art["numerales"] = numerales
        art["paragrafos"] = paragrafos
        notas = " | ".join(x for x in [notas, *notas_texto] if x)
        art["notas_vigencia"] = notas
        art["notas_articulo"] = notas_articulo
        estado, banderas, leyes, sentencias = vigencia_de(art["texto"], notas)
        # estado del artículo completo: vigente | vigente con cambios | inexequible | derogado
        art["vigencia"] = vigencia_articulo if vigencia_articulo in ("inexequible", "derogado") else estado
        art["observaciones_vigencia"] = banderas
        art["normas_modificatorias"] = leyes
        art["sentencias"] = sentencias
        art["temas"] = temas_de(art)
        art["n_palabras"] = len(art["texto"].split())
        articulos.append(art)

    for idx, linea in enumerate(lineas):
        if idx >= fin:
            break
        linea = linea.strip()
        if not linea:
            continue

        especial = especiales.get(idx)
        if especial and especial[0] in ("libro_nombre", "omitir"):
            continue
        if especial and especial[0] == "titulo":
            if art is not None:
                cerrar()
                art = None
            titulos_en_libro += 1
            ubic.update(titulo=a_romano(titulos_en_libro), capitulo=None)
            nombres.update(titulo=especial[1], capitulo="")
            esperando_nombre = None
            continue

        m_libro, m_tit, m_cap = RE_LIBRO.match(linea), RE_TITULO.match(linea), RE_CAPITULO.match(linea)
        if m_libro or m_tit or m_cap:
            if art is not None and not en_nota:
                cerrar()
                art = None
            if en_nota:
                continue
            if m_libro:
                ubic.update(libro=m_libro.group(1).title(), titulo=None, capitulo=None)
                nombre_libro = especial[1] if especial else ""
                nombres.update(libro=f"{m_libro.group(2)} {nombre_libro}".strip(), titulo="", capitulo="")
                titulos_en_libro = 0
                esperando_nombre = None if nombre_libro else "libro"
            elif m_tit:
                titulos_en_libro += 1
                ubic.update(titulo=m_tit.group(1), capitulo=None)
                nombres.update(titulo=m_tit.group(2), capitulo="")
                esperando_nombre = "titulo"
            else:
                ubic["capitulo"] = m_cap.group(1)
                nombres["capitulo"] = m_cap.group(2)
                esperando_nombre = "capitulo"
            continue

        m_art = RE_ARTICULO.match(linea)
        if m_art:
            num = int(m_art.group(1))
            if ultimo < num <= ultimo + 5:
                cerrar()
                en_nota = False
                esperando_nombre = None
                ultimo = num
                resto = m_art.group(2).strip()
                partes = re.split(r"(?<=\.)\s+", resto, maxsplit=1)
                if len(partes) == 2 and len(partes[0]) < 160:
                    epigrafe, inicio = partes[0].rstrip("."), partes[1]
                else:
                    epigrafe, inicio = (resto.rstrip("."), "") if len(resto) < 160 else ("", resto)
                art = {
                    "id": f"art_{num}",
                    "articulo": num,
                    "epigrafe": epigrafe,
                    "libro": ubic["libro"],
                    "libro_nombre": nombres["libro"].strip(". "),
                    "titulo": ubic["titulo"],
                    "titulo_nombre": nombres["titulo"].strip(". "),
                    "capitulo": ubic["capitulo"],
                    "capitulo_nombre": nombres["capitulo"].strip(". "),
                    "_lineas": [inicio] if inicio else [],
                    "_notas": [],
                }
                continue

        if esperando_nombre and es_mayuscula(linea):
            nombres[esperando_nombre] = f"{nombres[esperando_nombre]} {linea}".strip()
            continue
        esperando_nombre = None

        if art is None:
            continue
        m_nota = RE_NOTA.match(linea)
        if m_nota:
            en_nota = True
            nota_historica = bool(re.match(r"(?i)legislaci|texto original", linea))
        elif en_nota and not nota_historica and RE_PARAGRAFO.match(linea):
            en_nota = False
        if en_nota:
            art["_notas"].append(linea)
        else:
            art["_lineas"].append(linea)

    cerrar()
    return articulos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuente", default="Departamento Administrativo de la Función Pública - Gestor Normativo")
    ap.add_argument("--url", default="")
    ap.add_argument("--fecha", default=date.today().isoformat(), help="fecha de consulta AAAA-MM-DD")
    args = ap.parse_args()

    texto = ENTRADA.read_text(encoding="utf-8")
    articulos = segmentar(texto)

    corpus = {
        "metadatos": {
            "norma": "Ley 1801 de 2016 - Código Nacional de Seguridad y Convivencia Ciudadana",
            "fuente": args.fuente,
            "url": args.url,
            "fecha_consulta": args.fecha,
            "total_articulos": len(articulos),
            "esquema": "libro > titulo > capitulo > articulo > (inciso, numerales, paragrafos)",
        },
        "articulos": articulos,
    }
    SALIDA.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")

    encontrados = {a["articulo"] for a in articulos}
    faltan = [n for n in range(1, TOTAL_ARTICULOS + 1) if n not in encontrados]
    print(f"Corpus guardado en {SALIDA}")
    print(f"Artículos encontrados: {len(articulos)} de {TOTAL_ARTICULOS}")
    if faltan:
        print(f"Faltan ({len(faltan)}): {faltan[:40]}{' ...' if len(faltan) > 40 else ''}")
    print("Por libro:", dict(Counter(a["libro"] for a in articulos)))
    print("Por vigencia:", dict(Counter(a["vigencia"] for a in articulos)))
    titulos = {(a["libro"], a["titulo"], a["titulo_nombre"]) for a in articulos}
    print("Títulos por libro:", dict(Counter(t[0] for t in titulos)))
    print("Artículos sin título:", [a["articulo"] for a in articulos if not a["titulo"]])
    unidades = [u for a in articulos for u in a["numerales"] + a["paragrafos"]]
    print("Vigencia de numerales y parágrafos:", dict(Counter(u["vigencia"] for u in unidades)))
    print("Parágrafos:", sum(len(a["paragrafos"]) for a in articulos),
          "| Numerales:", sum(len(a["numerales"]) for a in articulos))
    sin_epigrafe = [a["articulo"] for a in articulos if not a["epigrafe"]]
    if sin_epigrafe:
        print("Sin epígrafe (revisar a mano):", sin_epigrafe[:30])


if __name__ == "__main__":
    main()
