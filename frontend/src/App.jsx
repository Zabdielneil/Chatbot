import { useEffect, useRef, useState } from "react";
import { preguntar, MODO_DEMO } from "./api.js";
import Mensaje from "./Mensaje.jsx";

const SUGERENCIAS = [
  "¿Qué es una medida correctiva y cuáles contempla el Código?",
  "¿Cuáles son los tipos de multa general?",
  "¿Qué puedo hacer si no estoy de acuerdo con una orden de comparendo?",
  "¿Puede la policía entrar a mi casa sin orden escrita?",
  "¿Está permitido consumir sustancias psicoactivas en parques?",
  "¿Qué dice el Código sobre perros potencialmente peligrosos?",
];

// El historial se guarda solo en el navegador de quien usa el chat (sessionStorage):
// no se envía ni se almacena en ningún servidor (Ley 1581 de 2012).
const CLAVE = "chat-ley1801";
function cargarHistorial() {
  try {
    return JSON.parse(sessionStorage.getItem(CLAVE)) || [];
  } catch {
    return [];
  }
}

export default function App() {
  const [mensajes, setMensajes] = useState(cargarHistorial);
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const finRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify(mensajes));
    } catch {}
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensajes, cargando]);

  async function enviar(pregunta) {
    pregunta = pregunta.trim();
    if (pregunta.length < 3 || cargando) return;
    setTexto("");
    setMensajes((m) => [...m, { rol: "usuario", texto: pregunta }]);
    setCargando(true);
    try {
      const r = await preguntar(pregunta);
      setMensajes((m) => [
        ...m,
        { rol: "bot", texto: r.respuesta, fuentes: r.fuentes || [], tiempo_ms: r.tiempo_ms },
      ]);
    } catch (e) {
      setMensajes((m) => [...m, { rol: "error", texto: e.message, pregunta }]);
    } finally {
      setCargando(false);
      inputRef.current?.focus();
    }
  }

  function reintentar(i) {
    const pregunta = mensajes[i].pregunta;
    setMensajes((m) => m.filter((_, j) => j !== i && j !== i - 1)); // quita la pregunta y el error
    enviar(pregunta);
  }

  return (
    <div className="app">
      <header className="cabecera">
        <div className="cabecera-fila">
          <div>
            <h1>Consulta el Código de Policía</h1>
            <p className="subtitulo">Ley 1801 de 2016 · Código Nacional de Seguridad y Convivencia Ciudadana</p>
          </div>
          {mensajes.length > 0 && (
            <button className="boton-secundario" onClick={() => setMensajes([])} disabled={cargando}>
              Nueva conversación
            </button>
          )}
        </div>
        <div className="aviso" role="note">
          <strong>Aviso:</strong> esta es una herramienta informativa y educativa. No sustituye la asesoría
          de un abogado ni la interpretación de las autoridades competentes.
          {MODO_DEMO && <span className="etiqueta-demo">MODO DEMO</span>}
        </div>
      </header>

      <main className="chat" aria-live="polite">
        {mensajes.length === 0 && (
          <div className="bienvenida">
            <p>
              Pregunta en tus propias palabras sobre multas, comparendos, comportamientos prohibidos,
              autoridades de policía o tus derechos. Cada respuesta cita los artículos de la ley y te muestra
              el texto en el que se basa.
            </p>
            <div className="sugerencias">
              {SUGERENCIAS.map((s) => (
                <button key={s} onClick={() => enviar(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {mensajes.map((m, i) => (
          <Mensaje key={i} mensaje={m} onReintentar={() => reintentar(i)} />
        ))}

        {cargando && (
          <div className="mensaje bot">
            <div className="burbuja escribiendo" aria-label="Buscando en el Código">
              <span /> <span /> <span />
            </div>
          </div>
        )}
        <div ref={finRef} />
      </main>

      <form
        className="entrada"
        onSubmit={(e) => {
          e.preventDefault();
          enviar(texto);
        }}
      >
        <textarea
          ref={inputRef}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar(texto);
            }
          }}
          placeholder="Escribe tu pregunta sobre el Código de Policía…"
          rows={1}
          maxLength={500}
          aria-label="Pregunta"
        />
        <button type="submit" disabled={cargando || texto.trim().length < 3}>
          Enviar
        </button>
      </form>
    </div>
  );
}
