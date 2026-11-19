"""Lexia: agente de IA que consulta el Código de Policía (Ley 1801 de 2016) y el Código de Tránsito
(Ley 769 de 2002) usando herramientas, en lugar de responder con una sola búsqueda.

El modelo (Groq, OpenAI o cualquier API compatible con OpenAI) decide qué herramientas usar:
    buscar_en_la_ley   búsqueda híbrida (FAISS + BM25) en una ley o en ambas
    leer_articulo      texto completo de un artículo, con numerales y parágrafos
    calcular_multa     valor en pesos de una multa expresada en salarios mínimos diarios
Puede buscar varias veces, reformular y leer artículos antes de responder o de armar un caso.

Uso de prueba (desde motor/):
    python src/agente.py "¿Cuándo me puede pedir la cédula un policía en la calle?"
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag import Motor, NO_ENCONTRADO  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
CORPUS = {
    "policia": BASE / "data" / "procesado" / "corpus.json",
    "transito": BASE / "data" / "procesado" / "corpus_transito.json",
}
NORMAS = {"policia": "Ley 1801 de 2016", "transito": "Ley 769 de 2002"}
SMMLV = float(os.getenv("SMMLV", "1750905"))  # salario mínimo mensual 2026 (COP)
MAX_RONDAS = int(os.getenv("AGENTE_MAX_RONDAS", "3"))
# gpt-oss razona antes de responder; "low" lo hace mucho más rápido (RNF1: < 10 s)
RAZONAMIENTO = os.getenv("AGENTE_RAZONAMIENTO", "low")
NO_ENCONTRADO_GENERAL = ("No encontré esa información en el Código de Policía (Ley 1801 de 2016) ni en el "
                         "Código de Tránsito (Ley 769 de 2002).")

PROMPT_LEXIA = f"""Eres Lexia, un asistente jurídico inteligente que explica a cualquier ciudadano dos normas colombianas:
- el Código Nacional de Seguridad y Convivencia Ciudadana (Ley 1801 de 2016, "Código de Policía"), y
- el Código Nacional de Tránsito Terrestre (Ley 769 de 2002).

PERSONALIDAD: abogado joven, experto, analítico y cercano. Profesional y respetuoso, pero sin sonar a documento \
de 200 páginas. Explicas con ejemplos cotidianos, eres preciso, imparcial (no juzgas ni tomas partido) y didáctico: \
explicas derechos, deberes, sanciones y procedimientos. Tuteas con respeto.

CÓMO TRABAJAS (obligatorio):
1. Antes de responder sobre la ley, USA las herramientas. Nunca respondas de memoria.
2. Si una búsqueda no trae lo que necesitas, reformula con términos jurídicos y busca otra vez. Ejemplos: \
"pedir la cédula" → "procedimiento de identificación", "registro a persona establecer la identidad"; \
"parte" → "orden de comparendo"; "pase" → "licencia de conducción"; "borracho" → "embriaguez". \
Si la pregunta puede tocar ambas leyes, busca en las dos.
3. Usa leer_articulo cuando necesites el detalle completo (numerales, parágrafos, tabla de multas).
4. Cita SIEMPRE la norma, el artículo y, si aplica, el numeral o parágrafo: \
(Ley 1801, Art. 35, num. 3) o (Ley 769, Art. 131, lit. C.29).
5. Responde SOLO con lo que digan los textos que obtuviste. No inventes artículos, multas, sentencias ni plazos, \
y NO agregues derechos, obligaciones o procedimientos que no aparezcan en esos textos (por ejemplo, no digas que \
el policía debe identificarse con placa si ningún texto lo dice).
6. Si la vigencia de un fragmento es "inexequible", di que la Corte Constitucional lo declaró inexequible y \
que ya no se aplica. Si dice "modificado" o "vigente con cambios", menciónalo si es relevante.
7. Si después de buscar la respuesta no está en ninguna de las dos leyes, responde exactamente: \
"{NO_ENCONTRADO_GENERAL}" y, si sirve, sugiere qué autoridad o norma podría resolverlo, sin inventar su contenido.
8. Los textos ya traen el valor en pesos de 2026 entre corchetes ("[≈ $233.456 COP en 2026]"): úsalo tal cual y NUNCA hagas cálculos tú. Para otros valores usa calcular_multa. Aclara que es un valor de referencia.
9. No das asesoría jurídica personalizada ni representas a nadie: eres una herramienta informativa y educativa.

FORMATO: español claro, en Markdown. Para preguntas simples, máximo unas 180 palabras: primero la respuesta \
directa, luego los detalles en una lista corta. No uses tablas salvo que te las pidan. \
Usa **negritas** para lo clave. Termina, cuando aplique, con una línea "📚 Fundamento:" con las citas.

CONSTRUCCIÓN Y ANÁLISIS DE CASOS
Cuando te pidan construir o analizar un caso:
1. Interpreta la solicitud: hechos, personajes, circunstancias y aspectos jurídicos.
2. Construye un escenario coherente, organizado y realista con la información dada.
3. Si hace falta, completa con detalles ficticios sin alterar los hechos principales, y márcalos como hipotéticos.
4. Identifica las cuestiones jurídicas y las normas aplicables (búscalas con las herramientas).
5. Fundamenta citando las disposiciones reales, separando hechos ficticios de fundamentos jurídicos reales.
6. Analiza consecuencias posibles: comportamientos o infracciones, medidas correctivas, multas, procedimiento, \
recursos y derechos de las personas involucradas, siempre sujetos a las circunstancias.
7. Cierra con una conclusión clara y lo que debe tenerse en cuenta.
Antes de redactar un caso, haz UNA búsqueda por cada hecho o conducta relevante (por ejemplo, una para "semáforo en rojo" en tránsito y otra para "negarse a identificarse" en policía). No afirmes que la ley no regula algo sin haberlo buscado. No menciones detenciones, penas ni procedimientos que no aparezcan en los textos obtenidos.
Modalidades: caso hipotético, caso práctico, caso jurídico estructurado (antecedentes, hechos, problema jurídico, \
fundamento normativo, análisis, conclusión), caso de estudio (con preguntas para discusión) o análisis de un caso \
existente (sin agregar circunstancias como si fueran reales).
Reglas: si hay datos suficientes, construye el caso sin preguntar; si faltan datos esenciales, pide solo esos. \
No confundas lo hipotético con hechos reales. No inventes leyes, artículos ni jurisprudencia. No declares \
automáticamente responsable a nadie: analiza circunstancias y posibles excepciones. Adapta la complejidad al usuario.
Formato de un caso: título "## 🗂️ Caso: ...", secciones con "###" (Hechos, Problema jurídico, Normas aplicables, \
Análisis, Consecuencias posibles, Derechos y recursos, Conclusión) y al final: \
"_Caso hipotético con fines educativos. No sustituye la asesoría de un abogado._"
"""

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "buscar_en_la_ley",
        "description": "Busca fragmentos (artículos, numerales, parágrafos) relevantes en el Código de Policía, "
                       "el Código de Tránsito o ambos. Usa términos jurídicos para mejores resultados.",
        "parameters": {"type": "object", "properties": {
            "consulta": {"type": "string", "description": "Qué buscar, en palabras clave o una frase"},
            "ley": {"type": "string", "enum": ["policia", "transito", "ambas"],
                    "description": "policia = Ley 1801 de 2016; transito = Ley 769 de 2002"},
        }, "required": ["consulta", "ley"]}}},
    {"type": "function", "function": {
        "name": "leer_articulo",
        "description": "Devuelve el texto completo de un artículo con sus numerales, parágrafos y vigencia.",
        "parameters": {"type": "object", "properties": {
            "ley": {"type": "string", "enum": ["policia", "transito"]},
            "articulo": {"type": "string", "description": "Número del artículo, p. ej. '35', '131' o '85A'"},
        }, "required": ["ley", "articulo"]}}},
    {"type": "function", "function": {
        "name": "calcular_multa",
        "description": "Convierte una multa expresada en salarios mínimos diarios legales vigentes (SMDLV/SMLDV) "
                       "a pesos colombianos con el salario mínimo de 2026.",
        "parameters": {"type": "object", "properties": {
            "salarios_minimos_diarios": {"type": "number", "description": "p. ej. 4 para Multa General tipo 2"},
        }, "required": ["salarios_minimos_diarios"]}}},
]

NUMEROS = {"uno": 1, "dos": 2, "cuatro": 4, "ocho": 8, "quince": 15, "treinta": 30, "cuarenta y cinco": 45}
SMDLV_MULTA_GENERAL = {"1": 2, "2": 4, "3": 8, "4": 16}  # Ley 1801, Art. 180


def pesos(smdlv):
    return f"${round(smdlv * SMMLV / 30):,.0f}".replace(",", ".")


def anotar_valores(texto):
    """Escribe junto a cada multa su valor en pesos de 2026, para que el modelo no tenga que calcular:
    'cuatro (4) salarios mínimos legales diarios' → '... [≈ $233.456 COP en 2026]'
    'Multa General tipo 2'                         → 'Multa General tipo 2 [4 SMDLV ≈ $233.456 COP en 2026]'"""
    texto = re.sub(r"(\((\d{1,3})\)\s*salarios\s+m[ií]nimos\s+(?:legales\s+)?diarios(?:\s+legales)?\s+vigentes(?:\s*\(\w+\))?)",
                   lambda m: f"{m.group(1)} [≈ {pesos(int(m.group(2)))} COP en 2026]", texto, flags=re.IGNORECASE)
    return re.sub(r"(Multa General tipo\s*([1-4]))(?!\s*\[)",
                  lambda m: f"{m.group(1)} [{SMDLV_MULTA_GENERAL[m.group(2)]} SMDLV ≈ "
                            f"{pesos(SMDLV_MULTA_GENERAL[m.group(2)])} COP en 2026]",
                  texto, flags=re.IGNORECASE)


ETIQUETA_LEY = {"policia": "el Código de Policía", "transito": "el Código de Tránsito", "ambas": "ambos códigos"}
DEL_LEY = {"policia": "del Código de Policía", "transito": "del Código de Tránsito"}


class Lexia:
    def __init__(self, motor=None):
        self.motor = motor or Motor()
        self.articulos = {}
        for ley, ruta in CORPUS.items():
            if ruta.exists():
                for a in json.loads(ruta.read_text(encoding="utf-8"))["articulos"]:
                    self.articulos[(ley, str(a["articulo"]).upper())] = a
        self.cliente = self.motor.cliente_llm
        self.modelo = self.motor.modelo_llm

    # ---------- herramientas ----------
    def buscar_en_la_ley(self, consulta, ley="ambas"):
        fuentes = self.motor._buscar(consulta, 14)["fuentes"]
        if ley in NORMAS:
            fuentes = [f for f in fuentes if f.get("norma") == NORMAS[ley]]
        fuentes = fuentes[:6]
        return {"resultados": [{
            "ref": f["ref"], "norma": f.get("norma"), "epigrafe": f["epigrafe"], "vigencia": f["vigencia"],
            "texto": anotar_valores(f["texto"][:380]),
            **({"medida_correctiva": anotar_valores(f["medida_correctiva"])} if f.get("medida_correctiva") else {}),
        } for f in fuentes]}, fuentes

    def leer_articulo(self, ley, articulo):
        a = self.articulos.get((ley, str(articulo).strip().upper().replace(" ", "")))
        if not a:
            return {"error": f"No existe el artículo {articulo} en {ETIQUETA_LEY.get(ley, ley)}."}, []
        partes = [f"Artículo {a['articulo']}. {a['epigrafe']} (vigencia: {a['vigencia']})", a.get("inciso") or ""]
        if any(n.get("grupo") for n in a["numerales"]):
            # tabla de multas de tránsito (Art. 131): resumen por grupo con su valor y algunos códigos.
            # Para una infracción concreta el modelo debe usar buscar_en_la_ley.
            grupos = {}
            for n in a["numerales"]:
                grupos.setdefault(n.get("grupo") or "", []).append(n)
            for grupo, codigos in grupos.items():
                ejemplos = "; ".join(f"{c['numeral']} {c['texto'][:60]}" for c in codigos[:4])
                partes.append(f"\nGRUPO {grupo[:230]} [{len(codigos)} infracciones. Ejemplos: {ejemplos}]")
        else:
            partes += [f"Numeral {n['numeral']} [{n.get('vigencia', 'vigente')}]: {n['texto']}" for n in a["numerales"]]
        partes += [f"Parágrafo {p['paragrafo']} [{p.get('vigencia', 'vigente')}]: {p['texto']}" for p in a["paragrafos"]]
        texto = "\n".join(x for x in partes if x)
        if not a["numerales"] and not a["paragrafos"]:
            texto = f"{partes[0]}\n{a['texto']}"
        prefijo = "" if ley == "policia" else "Ley 769 de 2002, "
        fuente = {"ref": f"{prefijo}Artículo {a['articulo']}", "norma": NORMAS[ley], "articulo": a["articulo"],
                  "epigrafe": a["epigrafe"], "texto": texto[:1500], "vigencia": a["vigencia"], "puntaje": 1.0,
                  "origen": "lectura"}
        return {"norma": NORMAS[ley], "texto": anotar_valores(texto[:4500])}, [fuente]

    @staticmethod
    def calcular_multa(salarios_minimos_diarios):
        smdlv = SMMLV / 30
        valor = round(float(salarios_minimos_diarios) * smdlv)
        return {"salarios_minimos_diarios": salarios_minimos_diarios,
                "valor_cop": valor, "valor_texto": f"${valor:,.0f} COP".replace(",", "."),
                "base": f"Salario mínimo mensual 2026: ${SMMLV:,.0f}; diario: ${smdlv:,.0f}".replace(",", "."),
                "nota": "Valor de referencia; el monto exacto lo liquida la autoridad competente."}, []

    def ejecutar(self, nombre, argumentos):
        try:
            args = json.loads(argumentos or "{}")
            if nombre == "buscar_en_la_ley":
                return self.buscar_en_la_ley(args.get("consulta", ""), args.get("ley", "ambas"))
            if nombre == "leer_articulo":
                return self.leer_articulo(args.get("ley", "policia"), args.get("articulo", ""))
            if nombre == "calcular_multa":
                return self.calcular_multa(args.get("salarios_minimos_diarios", 0))
            return {"error": f"Herramienta desconocida: {nombre}"}, []
        except Exception as e:  # argumentos mal formados, etc.
            return {"error": str(e)}, []

    @staticmethod
    def describir(nombre, argumentos):
        """Texto corto para que la interfaz muestre qué está haciendo Lexia."""
        try:
            a = json.loads(argumentos or "{}")
        except ValueError:
            a = {}
        if nombre == "buscar_en_la_ley":
            return f"Buscando en {ETIQUETA_LEY.get(a.get('ley'), 'la ley')}: “{a.get('consulta', '')}”"
        if nombre == "leer_articulo":
            return f"Leyendo el Artículo {a.get('articulo', '')} {DEL_LEY.get(a.get('ley'), 'de la ley')}"
        if nombre == "calcular_multa":
            return f"Calculando el valor de {a.get('salarios_minimos_diarios', '')} salarios mínimos diarios"
        return nombre

    # ---------- ciclo del agente ----------
    def conversar(self, historial):
        """Generador de eventos para la interfaz:
            {"tipo": "estado", "texto": ...}       qué está haciendo (buscar, leer, calcular)
            {"tipo": "fuentes", "fuentes": [...]}  fragmentos consultados (RF5)
            {"tipo": "respuesta", "texto": ...}    respuesta final en Markdown
            {"tipo": "fin", ...}                   tiempo y modelo
            {"tipo": "error", "texto": ...}
        historial: [{"rol": "usuario"|"lexia", "texto": "..."}] (el último es la pregunta)."""
        t0 = time.time()
        if self.cliente is None:
            yield {"tipo": "error", "texto": "Falta LLM_API_KEY en el .env: Lexia no puede razonar sin el modelo de IA."}
            return
        mensajes = [{"role": "system", "content": PROMPT_LEXIA}]
        for m in historial[-12:]:
            mensajes.append({"role": "user" if m.get("rol") == "usuario" else "assistant",
                             "content": str(m.get("texto", ""))[:4000]})
        fuentes, vistas = [], set()

        # Primera búsqueda automática en ambas leyes: el modelo arranca con contexto y, en preguntas
        # simples, responde en una sola llamada. Si no le sirve, usa las herramientas para buscar más.
        pregunta = mensajes[-1]["content"]
        yield {"tipo": "estado", "texto": "Buscando en el Código de Policía y el Código de Tránsito"}
        inicial, nuevas = self.buscar_en_la_ley(pregunta, "ambas")
        for f in nuevas:
            vistas.add(f["ref"])
            fuentes.append(f)
        mensajes[-1] = {"role": "user", "content": (
            f"{pregunta}\n\n[RESULTADOS INICIALES DE LA BÚSQUEDA: úsalos si responden la pregunta; si no, "
            f"busca de nuevo con otros términos. No agregues nada que no esté en los textos.]\n"
            f"{json.dumps(inicial, ensure_ascii=False)[:3500]}")}
        extra = {"reasoning_effort": RAZONAMIENTO} if "gpt-oss" in (self.modelo or "") else {}

        respuesta = ""
        for ronda in range(MAX_RONDAS + 1):
            ultima = ronda == MAX_RONDAS
            r = self.cliente.chat.completions.create(
                model=self.modelo, messages=mensajes, temperature=0.2, max_tokens=2500,
                tools=HERRAMIENTAS, tool_choice="none" if ultima else "auto", extra_body=extra)
            msg = r.choices[0].message
            llamadas = msg.tool_calls or []
            if not llamadas:
                respuesta = (msg.content or "").strip()
                break
            mensajes.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in llamadas]})
            for c in llamadas:
                yield {"tipo": "estado", "texto": self.describir(c.function.name, c.function.arguments)}
                resultado, nuevas = self.ejecutar(c.function.name, c.function.arguments)
                for f in nuevas:
                    if f["ref"] not in vistas:
                        vistas.add(f["ref"])
                        fuentes.append(f)
                mensajes.append({"role": "tool", "tool_call_id": c.id,
                                 "content": json.dumps(resultado, ensure_ascii=False)[:4500]})
            yield {"tipo": "estado", "texto": "Analizando lo que encontré"}

        yield {"tipo": "estado", "texto": "Redactando la respuesta"}
        respuesta = re.sub(r"\s*【[^】]*】", "", respuesta) or NO_ENCONTRADO_GENERAL
        # solo se muestran las fuentes que la respuesta cita, o todas si no cita ninguna
        citados = {m for m in re.findall(r"Art(?:\.|ículo)\s*(\d{1,3}[A-Z]?)", respuesta, re.IGNORECASE)}
        mostradas = [f for f in fuentes if str(f["articulo"]) in citados] or fuentes
        yield {"tipo": "fuentes", "fuentes": [
            {k: f.get(k) for k in ("ref", "norma", "articulo", "epigrafe", "texto", "vigencia", "puntaje",
                                   "medida_correctiva")} for f in mostradas[:12]]}
        yield {"tipo": "respuesta", "texto": respuesta}
        yield {"tipo": "fin", "tiempo_ms": int((time.time() - t0) * 1000), "modelo": self.modelo}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    lexia = Lexia()
    for evento in lexia.conversar([{"rol": "usuario", "texto": " ".join(sys.argv[1:])}]):
        if evento["tipo"] == "estado":
            print(f"  … {evento['texto']}")
        elif evento["tipo"] == "fuentes":
            print("\nFUENTES:", ", ".join(f["ref"] for f in evento["fuentes"]))
        elif evento["tipo"] == "respuesta":
            print("\n" + evento["texto"])
        elif evento["tipo"] == "fin":
            print(f"\n({evento['tiempo_ms']} ms, {evento['modelo']})")
        else:
            print(evento)


if __name__ == "__main__":
    main()
