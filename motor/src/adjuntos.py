"""Archivos que el usuario adjunta en el chat: se convierten en texto para que Lexia los analice con la ley.

- PDF: texto de las páginas (si es escaneado, se analiza la primera página como imagen)
- Word (.docx), .txt, .md, .csv, .json: texto
- Imágenes: modelo de visión (Groq) que transcribe el texto visible y describe la escena
- Videos y audios (notas de voz): se transcribe lo que se dice con Whisper (Groq); la imagen del video no se analiza

Privacidad (Ley 1581 de 2012): todo se procesa en memoria; ningún archivo se guarda en disco.
"""
import base64
import io
import os
import re
import zipfile

MAX_TEXTO = 6000
MODELO_VISION = os.getenv("LLM_MODELO_VISION", "qwen/qwen3.8-27b")
MODELO_AUDIO = os.getenv("LLM_MODELO_AUDIO", "whisper-large-v3-turbo")
PROMPT_VISION = (
    "Eres el asistente de un chatbot jurídico colombiano. Describe esta imagen en español, de forma objetiva y "
    "breve (máximo 200 palabras): 1) transcribe todo el texto visible (por ejemplo, un comparendo, una señal, una "
    "placa o un documento); 2) describe la escena y los elementos relevantes para normas de convivencia o de "
    "tránsito (vehículos, señales, personas, lugar). No identifiques a personas ni hagas suposiciones sobre ellas."
)


def _imagen_a_jpeg(datos, ext):
    """Reduce la imagen (máx. 1280 px) y la pasa a JPEG con PyMuPDF, para no exceder el límite de la API."""
    import pymupdf
    doc = pymupdf.open(stream=datos, filetype=ext or "png")
    pagina = doc[0]
    escala = min(1.0, 1280 / max(pagina.rect.width, pagina.rect.height))
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
    return pix.tobytes("jpeg")


def _describir_imagen(cliente, jpeg):
    if cliente is None:
        return None, "Falta LLM_API_KEY: no se puede analizar la imagen."
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    try:
        r = cliente.chat.completions.create(
            model=MODELO_VISION, temperature=0.2, max_tokens=500,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": PROMPT_VISION},
                {"type": "image_url", "image_url": {"url": url}},
            ]}])
        texto = re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S)
        return texto.strip(), None
    except Exception as e:  # modelo no disponible, imagen inválida, límite del proveedor...
        return None, f"No se pudo analizar la imagen ({str(e)[:120]})."


def _transcribir(cliente, nombre, datos):
    if cliente is None:
        return None, "Falta LLM_API_KEY: no se puede transcribir el audio."
    try:
        r = cliente.audio.transcriptions.create(model=MODELO_AUDIO, file=(nombre, datos), language="es")
        return (r.text or "").strip(), None
    except Exception as e:
        return None, f"No se pudo transcribir el audio ({str(e)[:120]})."


def _texto_docx(datos):
    with zipfile.ZipFile(io.BytesIO(datos)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def procesar(nombre, tipo_mime, datos, cliente_llm):
    """Devuelve {"nombre", "tipo", "texto", "nota"}; "texto" es lo que se le entrega a Lexia."""
    nombre = os.path.basename(nombre or "archivo")
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    tipo_mime = tipo_mime or ""
    texto, nota, tipo = "", "", "archivo"

    try:
        if tipo_mime.startswith("image/") or ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
            tipo = "imagen"
            texto, nota = _describir_imagen(cliente_llm, _imagen_a_jpeg(datos, ext if ext != "jpeg" else "jpg"))
            texto = f"Descripción automática de la imagen: {texto}" if texto else ""
        elif tipo_mime.startswith(("video/", "audio/")) or ext in ("mp4", "mov", "webm", "mp3", "m4a", "ogg",
                                                                     "opus", "wav", "flac", "mpeg", "mpga"):
            tipo = "video" if tipo_mime.startswith("video/") or ext in ("mp4", "mov", "webm") else "audio"
            dicho, nota = _transcribir(cliente_llm, nombre, datos)
            if dicho:
                texto = f"Transcripción de lo que se dice en el {tipo}: {dicho}"
                if tipo == "video":
                    nota = "Lexia escuchó el audio del video, pero no puede ver las imágenes: describe lo que pasa si es importante."
            elif not nota:
                nota = "No se escuchó nada en el archivo. Describe con tus palabras lo que ocurre."
        elif ext == "pdf" or tipo_mime == "application/pdf":
            tipo = "pdf"
            import pymupdf
            doc = pymupdf.open(stream=datos, filetype="pdf")
            texto = "\n".join(p.get_text() for p in list(doc)[:15]).strip()
            if len(texto) < 40 and len(doc):  # PDF escaneado: se analiza la primera página como imagen
                jpeg = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes("jpeg")
                desc, nota = _describir_imagen(cliente_llm, jpeg)
                texto = f"PDF escaneado. Descripción de la primera página: {desc}" if desc else ""
        elif ext == "docx":
            tipo = "documento"
            texto = _texto_docx(datos)
        elif tipo_mime.startswith("text/") or ext in ("txt", "md", "csv", "json"):
            tipo = "texto"
            texto = datos.decode("utf-8", errors="replace")
        else:
            nota = "Este tipo de archivo no se puede leer. Prueba con una imagen, un PDF, un Word o un texto."
    except Exception as e:
        nota = f"No se pudo leer el archivo ({str(e)[:120]})."

    texto = re.sub(r"[ \t]+", " ", texto or "").strip()
    if len(texto) > MAX_TEXTO:
        texto = texto[:MAX_TEXTO] + " […]"
    return {"nombre": nombre, "tipo": tipo, "texto": texto, "nota": nota or ""}
