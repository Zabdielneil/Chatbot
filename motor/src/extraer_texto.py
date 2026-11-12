"""Paso 1: saca el texto de la ley (PDF, HTML o TXT) y lo limpia.

Uso:
    python src/extraer_texto.py data/raw/Ley_1801_de_2016.pdf
"""
import re
import sys
import unicodedata
from pathlib import Path

SALIDA = Path(__file__).resolve().parents[1] / "data" / "procesado" / "ley1801_limpio.txt"

# encabezados, pies y basura que meten las fuentes oficiales en cada página
RUIDO = [
    r"^Departamento Administrativo de la Funci[oó]n P[uú]blica\s*$",
    r"^Ley 1801 de 2016\s+\d+\s+EVA - Gestor Normativo\s*$",
    r"^Ley 1801 de 2016(\s+\d+)?\s*$",  # encabezado suelto que se cuela entre páginas
    r"^EVA - Gestor Normativo\s*$",
    r"^Fecha y hora de creaci[oó]n:.*$",
    r"^Los datos publicados tienen prop[oó]sitos exclusivamente informativos.*$",
    r"^responsable de la vigencia de la presente norma.*$",
    r"^\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}.*$",
    r"^https?://\S+$",
    r"^P[aá]gina\s+\d+(\s+de\s+\d+)?\s*$",
    r"^\d{1,3}\s*$",
]
RUIDO = [re.compile(p, re.IGNORECASE) for p in RUIDO]


def leer_pdf(ruta):
    import pymupdf
    doc = pymupdf.open(ruta)
    return "\n".join(p.get_text() for p in doc)


def leer_html(ruta):
    from bs4 import BeautifulSoup
    html = Path(ruta).read_bytes()
    sopa = BeautifulSoup(html, "html.parser")
    for t in sopa(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    return sopa.get_text("\n")


# ligaduras tipográficas del PDF: "ﬁsiológicas" (1 carácter) → "fisiológicas" (2 letras)
LIGADURAS = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
             "\ufb05": "st", "\ufb06": "st"}


def limpiar(texto):
    texto = unicodedata.normalize("NFC", texto)
    for lig, letras in LIGADURAS.items():
        texto = texto.replace(lig, letras)
    texto = texto.replace(" ", " ").replace("­", "").replace("�", "")
    texto = re.sub(r"[​-‏﻿]", "", texto)
    lineas = []
    for linea in texto.splitlines():
        linea = re.sub(r"[ \t]+", " ", linea).strip()
        if any(p.match(linea) for p in RUIDO):
            continue
        lineas.append(linea)
    texto = "\n".join(lineas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # palabras partidas con guion al final de línea
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
    return texto.strip()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ruta = Path(sys.argv[1])
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        crudo = leer_pdf(ruta)
    elif ext in (".html", ".htm"):
        crudo = leer_html(ruta)
    else:
        crudo = ruta.read_text(encoding="utf-8", errors="replace")

    limpio = limpiar(crudo)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(limpio, encoding="utf-8")
    print(f"Texto limpio guardado en {SALIDA}")
    print(f"Caracteres antes: {len(crudo):,} | después: {len(limpio):,}")


if __name__ == "__main__":
    main()
