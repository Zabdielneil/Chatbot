// Comunicación con el backend de Node.
//   POST /api/agente → Lexia (agente con herramientas), responde como Server-Sent Events
// Con VITE_DEMO=true en el .env se simulan los eventos, para trabajar la interfaz sin motor ni backend.

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3001";
export const MODO_DEMO = import.meta.env.VITE_DEMO === "true";

/**
 * Envía la conversación a Lexia y va llamando a onEvento con cada evento:
 *   {tipo:"estado", texto} | {tipo:"fuentes", fuentes} | {tipo:"respuesta", texto} | {tipo:"fin"} | {tipo:"error", texto}
 * mensajes: [{rol:"usuario"|"lexia", texto}]
 */
export async function conversar(mensajes, onEvento, signal) {
  if (MODO_DEMO) return demo(mensajes, onEvento);

  let r;
  try {
    r = await fetch(`${API_URL}/api/agente`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensajes }),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    throw new Error(`No pude conectarme con el servidor (${API_URL}). ¿Está corriendo el backend?`);
  }
  if (!r.ok) {
    const datos = await r.json().catch(() => ({}));
    throw new Error(datos.error || `Error ${r.status} del servidor`);
  }

  const lector = r.body.getReader();
  const decodificador = new TextDecoder();
  let pendiente = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    pendiente += decodificador.decode(value, { stream: true });
    const bloques = pendiente.split("\n\n");
    pendiente = bloques.pop();
    for (const bloque of bloques) {
      const linea = bloque.split("\n").find((l) => l.startsWith("data:"));
      if (!linea) continue;
      try {
        const evento = JSON.parse(linea.slice(5).trim());
        if (evento.tipo === "error") throw new Error(evento.texto);
        onEvento(evento);
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}

// ---------- modo demo (textos de ejemplo, NO son la ley) ----------
const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function demo(mensajes, onEvento) {
  const pregunta = mensajes[mensajes.length - 1].texto;
  const caso = /caso/i.test(pregunta);
  const pasos = caso
    ? ["Analizando tu pregunta", "Buscando en ambos códigos: “riña embriaguez”", "Leyendo el Artículo 27 del Código de Policía", "Redactando el caso"]
    : ["Analizando tu pregunta", "Buscando en el Código de Policía: “procedimiento de identificación”", "Leyendo el Artículo 35 del Código de Policía", "Redactando la respuesta"];
  for (const p of pasos) {
    onEvento({ tipo: "estado", texto: p });
    await esperar(700);
  }
  onEvento({
    tipo: "fuentes",
    fuentes: [
      { ref: "Artículo 35, numeral 3", norma: "Ley 1801 de 2016", articulo: 35, epigrafe: "Comportamientos que afectan las relaciones entre las personas y las autoridades", texto: "[Texto de ejemplo del modo demo]", vigencia: "vigente", puntaje: 0.71 },
      { ref: "Ley 769 de 2002, Artículo 131, numeral C.29", norma: "Ley 769 de 2002", articulo: 131, epigrafe: "Multas", texto: "[Texto de ejemplo del modo demo]", vigencia: "vigente con cambios", puntaje: 0.64 },
    ],
  });
  onEvento({
    tipo: "respuesta",
    texto: caso
      ? "## 🗂️ Caso: Ejemplo del modo demo\n\n### Hechos\nUna persona hipotética… **(modo demo)**\n\n### Normas aplicables\n- (Ley 1801, Art. 35, num. 3)\n\n### Conclusión\nAsí se verá un caso armado por Lexia.\n\n_Caso hipotético con fines educativos. No sustituye la asesoría de un abogado._"
      : "**[MODO DEMO]** Así se verá una respuesta de Lexia: explicación sencilla, con **negritas** en lo clave y la cita al final.\n\n- Primer punto importante\n- Segundo punto\n\n📚 Fundamento: (Ley 1801, Art. 35, num. 3) y (Ley 769, Art. 131, lit. C.29)",
  });
  onEvento({ tipo: "fin", tiempo_ms: 2800, modelo: "demo" });
}
