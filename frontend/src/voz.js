// Voz en el navegador (sin servidor ni costo): Web Speech API.
//   dictado: SpeechRecognition (Chrome y Edge)
//   lectura: speechSynthesis (todos los navegadores modernos)
// No se guarda ni se envía el audio a nuestro servidor: el navegador lo convierte en texto.

const Reconocimiento = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
export const puedeDictar = Boolean(Reconocimiento);
export const puedeLeer = typeof window !== "undefined" && "speechSynthesis" in window;

/** Empieza a escuchar. onTexto(texto, final) se llama con lo que va entendiendo. Devuelve una función para parar. */
export function dictar({ onTexto, onFin, onError }) {
  const rec = new Reconocimiento();
  rec.lang = "es-CO";
  rec.interimResults = true;
  rec.continuous = true;
  let acumulado = "";
  rec.onresult = (e) => {
    let parcial = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) acumulado += t + " ";
      else parcial += t;
    }
    onTexto((acumulado + parcial).trim());
  };
  rec.onerror = (e) => onError?.(e.error === "not-allowed" ? "Permite el uso del micrófono en el navegador." : "No pude escucharte bien. Intenta de nuevo.");
  rec.onend = () => onFin?.(acumulado.trim());
  rec.start();
  return () => rec.stop();
}

/** Texto plano para leer en voz alta (sin Markdown ni emojis). */
function limpiar(md) {
  return md
    .replace(/[#*_`>|]/g, " ")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\bArt\./g, "artículo")
    .replace(/\bnum\./g, "numeral")
    .replace(/\bpar\./g, "parágrafo")
    .replace(/\blit\./g, "literal")
    .replace(/SMDLV|SMLDV/g, "salarios mínimos diarios")
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function leer(texto, onFin) {
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(limpiar(texto));
  u.lang = "es-CO";
  const voces = window.speechSynthesis.getVoices();
  u.voice = voces.find((v) => v.lang === "es-CO") || voces.find((v) => v.lang?.startsWith("es")) || null;
  u.rate = 1.05;
  u.onend = onFin;
  u.onerror = onFin;
  window.speechSynthesis.speak(u);
}

export function callar() {
  if (puedeLeer) window.speechSynthesis.cancel();
}
