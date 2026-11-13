// Comunicación con el backend de Node (POST /api/chat).
// Con VITE_DEMO=true en el .env responde con datos de ejemplo, para trabajar el frontend
// sin tener levantados el motor Python ni el backend.

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3001";
export const MODO_DEMO = import.meta.env.VITE_DEMO === "true";

// k es opcional: sin él, el motor usa su valor por defecto
export async function preguntar(pregunta, k) {
  if (MODO_DEMO) return respuestaDemo(pregunta);

  let r;
  try {
    r = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta, k }),
      signal: AbortSignal.timeout(45000),
    });
  } catch (e) {
    throw new Error(
      e.name === "TimeoutError"
        ? "La consulta tardó demasiado. Intenta de nuevo."
        : `No se pudo conectar con el servidor (${API_URL}). ¿Está corriendo el backend?`
    );
  }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.error || `Error ${r.status} del servidor`);
  return datos;
}

export async function estado() {
  if (MODO_DEMO) return { backend: "demo", motor: "demo" };
  const r = await fetch(`${API_URL}/api/health`, { signal: AbortSignal.timeout(4000) });
  return r.json();
}

// ---------- modo demo ----------
// Textos de relleno claramente marcados: NO son el texto de la ley.
function respuestaDemo(pregunta) {
  const fuera = /tr[aá]nsito|impuesto|renta|predial|divorcio|pase|licencia de conducci/i.test(pregunta);
  const datos = fuera
    ? {
        respuesta:
          "No encontré esa información en el Código Nacional de Seguridad y Convivencia Ciudadana (Ley 1801 de 2016).",
        fuentes: [],
      }
    : {
        respuesta:
          "[MODO DEMO] Esta es una respuesta de ejemplo para probar la interfaz. Aquí el modelo explicaría el tema en lenguaje sencillo citando los artículos, por ejemplo (Art. 140, num. 4) y (Art. 180, par. 1).",
        fuentes: [
          {
            ref: "Artículo 140, numeral 4",
            articulo: 140,
            epigrafe: "Comportamientos contrarios al cuidado e integridad del espacio público",
            texto: "[Texto de ejemplo: aquí aparecerá el texto real del numeral recuperado por FAISS.]",
            vigencia: "vigente",
            puntaje: 0.71,
          },
          {
            ref: "Artículo 180, parágrafo 1",
            articulo: 180,
            epigrafe: "Multas",
            texto: "[Texto de ejemplo: aquí aparecerá el texto real del parágrafo recuperado.]",
            vigencia: "vigente con cambios",
            puntaje: 0.64,
          },
        ],
      };
  return new Promise((ok) =>
    setTimeout(
      () =>
        ok({
          pregunta,
          ...datos,
          tiempo_ms: 900,
          modelo_llm: "demo",
          aviso: "Herramienta informativa. No sustituye la asesoría de un abogado.",
        }),
      900
    )
  );
}
