import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { conversar, subirAdjunto, MODO_DEMO } from "./api.js";
import { dictar, puedeDictar, callar } from "./voz.js";
import Avatar from "./Avatar.jsx";
import Mensaje from "./Mensaje.jsx";

const SUGERENCIAS = [
  { icono: "👮", titulo: "Identificación", texto: "¿Cuándo me puede pedir la cédula un policía en la calle?" },
  { icono: "🚦", titulo: "Tránsito", texto: "¿Cuánto es la multa por pasarse un semáforo en rojo?" },
  { icono: "🍺", titulo: "Espacio público", texto: "¿Puedo tomar cerveza en un parque?" },
  { icono: "🐕", titulo: "Mascotas", texto: "¿Qué pasa si saco a mi pitbull sin bozal?" },
  { icono: "📄", titulo: "Comparendos", texto: "¿Qué hago si no estoy de acuerdo con un comparendo?" },
  { icono: "🏠", titulo: "Domicilio", texto: "¿Puede la policía entrar a mi casa sin orden?" },
];

const ATAJOS = [
  { icono: "🗂️", texto: "Armar un caso", caso: true },
  { icono: "🚗", texto: "Multas de tránsito", pregunta: "¿Cuáles son los tipos de multa de tránsito y cuánto valen?" },
  { icono: "👮", texto: "Mis derechos ante la policía", pregunta: "¿Qué derechos tengo cuando la policía me aborda en la calle?" },
  { icono: "⚖️", texto: "Medidas correctivas", pregunta: "¿Qué son las medidas correctivas y cuáles existen?" },
];

// El historial vive solo en esta pestaña del navegador (sessionStorage): no se guarda en ningún
// servidor, por la Ley 1581 de 2012 de protección de datos.
const CLAVE = "lexia-chat";
const MAX_ADJUNTOS = 3;
const ACEPTA = "image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.md,.csv,.json";
const tipoDe = (f) => (f.type.startsWith("image/") ? "imagen" : f.type.startsWith("video/") ? "video"
  : f.type.startsWith("audio/") ? "audio" : /pdf$/i.test(f.name) ? "pdf" : "archivo");
const ICONO = { imagen: "🖼️", video: "🎬", audio: "🎙️", pdf: "📕", archivo: "📄" };
const cargar = () => {
  try {
    return JSON.parse(sessionStorage.getItem(CLAVE)) || [];
  } catch {
    return [];
  }
};

/** Historial que se envía a Lexia: solo pares pregunta-respuesta (se omiten las preguntas que fallaron). */
function historialParaLexia(mensajes) {
  return mensajes
    .filter((m, i) => m.rol === "lexia" || (m.rol === "usuario" && mensajes[i + 1]?.rol !== "error"))
    .map(({ rol, texto, contexto }) => ({ rol, texto: contexto ? `${texto}${contexto}` : texto }));
}

function PantallaCarga({ saliendo }) {
  return (
    <div className={`carga ${saliendo ? "carga--sale" : ""}`} aria-hidden="true">
      <div className="carga__centro">
        <Avatar tamano={120} estado="pensando" />
        <svg className="carga__balanza" viewBox="0 0 64 40" width="64" height="40">
          <path d="M32 4v32M14 36h36M8 12h48M14 12l-7 14h14zM50 12l-7 14h14z" />
        </svg>
        <h1 className="carga__nombre">Lexia</h1>
        <p className="carga__lema">Tu asistente jurídico inteligente</p>
        <div className="carga__barra"><span /></div>
      </div>
    </div>
  );
}

export default function App() {
  const [mensajes, setMensajes] = useState(cargar);
  const [texto, setTexto] = useState("");
  const [progreso, setProgreso] = useState(null); // {pasos: []} mientras Lexia trabaja
  const [modoCaso, setModoCaso] = useState(false);
  const [carga, setCarga] = useState("visible"); // visible → saliendo → oculta
  const [escuchando, setEscuchando] = useState(false);
  const [avisoVoz, setAvisoVoz] = useState("");
  const [abajo, setAbajo] = useState(true);
  const [adjuntos, setAdjuntos] = useState([]); // {id, nombre, tipo, url, estado: subiendo|listo|error, texto, nota}
  const [arrastrando, setArrastrando] = useState(false);
  const archivoRef = useRef(null);
  const listaRef = useRef(null);
  const entradaRef = useRef(null);
  const abortRef = useRef(null);
  const pararRef = useRef(null);
  const ocupado = progreso !== null;

  useEffect(() => {
    const t1 = setTimeout(() => setCarga("saliendo"), 1500);
    const t2 = setTimeout(() => setCarga("oculta"), 2100);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify(mensajes));
    } catch {}
  }, [mensajes]);

  // desplazamiento automático al final, como en una app de mensajería
  const bajar = useCallback((suave = true) => {
    const el = listaRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: suave ? "smooth" : "auto" });
  }, []);
  useLayoutEffect(() => {
    if (abajo) bajar();
  }, [mensajes, progreso, abajo, bajar]);
  useEffect(() => bajar(false), [bajar]);

  function alDesplazar() {
    const el = listaRef.current;
    setAbajo(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }

  // el cuadro de texto crece con el contenido; la barra de desplazamiento solo aparece al llegar al máximo
  useEffect(() => {
    const el = entradaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    el.style.overflowY = el.scrollHeight > 160 ? "auto" : "hidden";
  }, [texto]);

  function agregarArchivos(lista) {
    const nuevos = [...lista].slice(0, MAX_ADJUNTOS - adjuntos.length).map((f) => ({
      id: `${Date.now()}-${Math.random()}`, nombre: f.name, tipo: tipoDe(f),
      url: URL.createObjectURL(f), estado: "subiendo", archivo: f,
    }));
    if (!nuevos.length) return;
    setAdjuntos((a) => [...a, ...nuevos]);
    for (const n of nuevos) {
      subirAdjunto(n.archivo)
        .then((r) => setAdjuntos((a) => a.map((x) => (x.id === n.id
          ? { ...x, estado: r.texto ? "listo" : "error", texto: r.texto, nota: r.nota } : x))))
        .catch((e) => setAdjuntos((a) => a.map((x) => (x.id === n.id ? { ...x, estado: "error", nota: e.message } : x))));
    }
  }

  const subiendo = adjuntos.some((a) => a.estado === "subiendo");
  const listos = adjuntos.filter((a) => a.estado === "listo");

  async function enviar(contenido) {
    let pregunta = (contenido ?? texto).trim();
    if (contenido === undefined && !pregunta && listos.length) {
      pregunta = "Analiza este archivo según el Código de Policía y el Código de Tránsito.";
    }
    if (pregunta.length < 3 || ocupado || subiendo) return;
    if (modoCaso && contenido === undefined && !/caso/i.test(pregunta)) {
      pregunta = `Construye un caso jurídico estructurado sobre: ${pregunta}`;
    }
    pararRef.current?.();
    callar();
    setTexto("");
    setModoCaso(false);
    setAbajo(true);
    // el contenido de los archivos va a Lexia como contexto; en la burbuja solo se ve la vista previa
    const usados = contenido === undefined ? adjuntos.filter((a) => a.estado !== "subiendo") : [];
    const contexto = usados.map((a) => `

[ARCHIVO ADJUNTO: ${a.nombre} (${a.tipo})]
${a.texto || a.nota || "No se pudo leer."}`).join("");
    if (contenido === undefined) setAdjuntos([]);
    const historial = [...mensajes, {
      rol: "usuario", texto: pregunta, t: Date.now(), contexto: contexto || undefined,
      adjuntos: usados.length ? usados.map(({ nombre, tipo, url, nota, estado }) => ({ nombre, tipo, url, nota, estado })) : undefined,
    }];
    setMensajes(historial);
    setProgreso({ pasos: [] });

    const pasos = [];
    let fuentes = [];
    let respuesta = "";
    let tiempo = null;
    const control = new AbortController();
    abortRef.current = control;
    try {
      await conversar(
        historialParaLexia(historial),
        (e) => {
          if (e.tipo === "estado") {
            pasos.push(e.texto);
            setProgreso({ pasos: [...pasos] });
          } else if (e.tipo === "fuentes") fuentes = e.fuentes;
          else if (e.tipo === "respuesta") respuesta = e.texto;
          else if (e.tipo === "fin") tiempo = e.tiempo_ms;
        },
        control.signal
      );
      if (control.signal.aborted) return;
      if (!respuesta) throw new Error("Lexia tardó demasiado en responder. Intenta de nuevo.");
      setMensajes((m) => [...m, {
        rol: "lexia", texto: respuesta, fuentes,
        pasos: pasos.filter((p) => !/^(Analizando|Redactando)/.test(p)), tiempo_ms: tiempo, t: Date.now(),
      }]);
    } catch (e) {
      if (!control.signal.aborted) setMensajes((m) => [...m, { rol: "error", texto: e.message, pregunta, t: Date.now() }]);
    } finally {
      if (abortRef.current === control) {
        setProgreso(null);
        abortRef.current = null;
      }
      entradaRef.current?.focus();
    }
  }

  function reintentar(i) {
    const { pregunta } = mensajes[i];
    setMensajes((m) => m.filter((_, j) => j !== i && j !== i - 1));
    setTimeout(() => enviar(pregunta), 0);
  }

  function atajo(a) {
    if (a.pregunta) return enviar(a.pregunta);
    setModoCaso(true);
    entradaRef.current?.focus();
  }

  function nueva() {
    abortRef.current?.abort();
    abortRef.current = null;
    callar();
    setMensajes([]);
    setProgreso(null);
  }

  function microfono() {
    if (escuchando) return pararRef.current?.();
    setAvisoVoz("");
    const base = texto ? `${texto.trim()} ` : "";
    setEscuchando(true);
    pararRef.current = dictar({
      onTexto: (t) => setTexto(base + t),
      onFin: () => {
        setEscuchando(false);
        pararRef.current = null;
        entradaRef.current?.focus();
      },
      onError: (msg) => setAvisoVoz(msg),
    });
  }

  const ultimoPaso = progreso?.pasos.at(-1) || "Analizando tu pregunta";
  const estadoAvatar = !ocupado ? "reposo" : /Redactando/.test(ultimoPaso) ? "hablando" : "pensando";
  const estadoTexto = escuchando ? "escuchándote…" : !ocupado ? "En línea" : /Redactando/.test(ultimoPaso) ? "escribiendo…" : "consultando la ley…";

  return (
    <>
      {carga !== "oculta" && <PantallaCarga saliendo={carga === "saliendo"} />}
      <div className={`app ${carga === "oculta" ? "app--lista" : ""}`}>
        {/* ---------- perfil de Lexia ---------- */}
        <aside className="perfil">
          <div className="perfil__tarjeta">
            <Avatar estado={estadoAvatar} tamano={132} />
            <h1 className="perfil__nombre">Lexia <span className="verificado" title="Asistente verificado">✓</span></h1>
            <p className="perfil__rol">Tu asistente jurídico inteligente</p>
            <p className={`perfil__estado ${ocupado ? "perfil__estado--activo" : ""}`}>
              <span className="punto" /> <span className="perfil__estado-texto">{ocupado ? ultimoPaso : "En línea · lista para ayudarte"}</span>
            </p>
            <div className="perfil__leyes">
              <span className="ley-chip">🛡️ Código de Policía <small>Ley 1801 de 2016</small></span>
              <span className="ley-chip ley-chip--transito">🚦 Código de Tránsito <small>Ley 769 de 2002</small></span>
            </div>
          </div>

          <nav className="atajos" aria-label="Atajos">
            <p className="atajos__titulo">¿Qué quieres hacer?</p>
            {ATAJOS.map((a, i) => (
              <button key={a.texto} className="atajo" style={{ "--i": i }} onClick={() => atajo(a)} disabled={ocupado}>
                <span className="atajo__icono">{a.icono}</span>{a.texto}
              </button>
            ))}
          </nav>

          <p className="perfil__aviso">
            ⚖️ Herramienta informativa y educativa. No sustituye la asesoría de un abogado ni la interpretación de las
            autoridades competentes.
          </p>
        </aside>

        {/* ---------- chat ---------- */}
        <main
          className={`chat ${arrastrando ? "chat--soltar" : ""}`}
          onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setArrastrando(true); } }}
          onDragLeave={(e) => { if (e.currentTarget === e.target) setArrastrando(false); }}
          onDrop={(e) => { e.preventDefault(); setArrastrando(false); agregarArchivos(e.dataTransfer.files); }}
        >
          {arrastrando && <div className="soltar">📎 Suelta aquí tus fotos, videos, audios o documentos</div>}
          <header className="chat__cabecera">
            <Avatar estado={estadoAvatar} tamano={42} conHalo={false} />
            <div className="chat__titulo">
              <strong>Lexia {MODO_DEMO && <span className="demo">DEMO</span>}</strong>
              <span className={ocupado || escuchando ? "escribiendo" : ""}>{estadoTexto}</span>
            </div>
            <button className="boton-suave" onClick={nueva} disabled={mensajes.length === 0 && !ocupado}>
              ＋ Nueva
            </button>
          </header>

          <div className="aviso-movil">⚖️ Información educativa. No sustituye la asesoría de un abogado.</div>

          <section className="chat__mensajes" ref={listaRef} onScroll={alDesplazar} aria-live="polite">
            {mensajes.length === 0 && !ocupado && (
              <div className="bienvenida">
                <div className="bienvenida__avatar"><Avatar tamano={96} /></div>
                <h2>Hola, soy <span className="gradiente">Lexia</span> 👋</h2>
                <p>
                  Te explico el <strong>Código de Policía</strong> y el <strong>Código de Tránsito</strong> sin
                  enredos: multas, comparendos, tus derechos y deberes. También puedo <strong>armarte un caso</strong>{" "}
                  para entender cómo se aplica la ley.
                </p>
                <div className="sugerencias">
                  {SUGERENCIAS.map((s, i) => (
                    <button key={s.texto} className="sugerencia" style={{ "--i": i }} onClick={() => enviar(s.texto)}>
                      <span className="sugerencia__icono">{s.icono}</span>
                      <span>
                        <small>{s.titulo}</small>
                        {s.texto}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {mensajes.length > 0 && <div className="dia"><span>Hoy</span></div>}

            {mensajes.map((m, i) => (
              <Mensaje key={i} mensaje={m} onReintentar={() => reintentar(i)} />
            ))}

            {ocupado && (
              <div className="fila fila--lexia">
                <Avatar estado={estadoAvatar} tamano={34} conHalo={false} />
                <div className="burbuja burbuja--lexia burbuja--trabajando">
                  <div className="trabajando">
                    <span className="puntos"><i /><i /><i /></span>
                    <span key={ultimoPaso} className="trabajando__texto">{ultimoPaso}</span>
                  </div>
                  {progreso.pasos.length > 1 && (
                    <ol className="pasos pasos--vivo">
                      {progreso.pasos.slice(0, -1).filter((p) => !/^Analizando/.test(p)).map((p, i) => <li key={i}>{p}</li>)}
                    </ol>
                  )}
                </div>
              </div>
            )}
          </section>

          {!abajo && (
            <button className="ir-abajo" onClick={() => { setAbajo(true); bajar(); }} aria-label="Ir al último mensaje">↓</button>
          )}

          <form className="redactor" onSubmit={(e) => { e.preventDefault(); enviar(); }}>
            {modoCaso && (
              <div className="redactor__modo">
                🗂️ Modo caso: describe la situación y Lexia arma el caso
                <button type="button" onClick={() => setModoCaso(false)} aria-label="Salir del modo caso">✕</button>
              </div>
            )}
            {(escuchando || avisoVoz) && (
              <div className={`redactor__voz ${avisoVoz ? "redactor__voz--error" : ""}`}>
                {avisoVoz || (<><span className="ondas"><i /><i /><i /><i /><i /></span> Te escucho… toca el micrófono para terminar</>)}
              </div>
            )}
            {adjuntos.length > 0 && (
              <div className="adjuntos">
                {adjuntos.map((a) => (
                  <div key={a.id} className={`adjunto adjunto--${a.estado}`} title={a.nota || a.nombre}>
                    {a.tipo === "imagen" ? <img src={a.url} alt="" /> : <span className="adjunto__icono">{ICONO[a.tipo]}</span>}
                    <span className="adjunto__info">
                      <span className="adjunto__nombre">{a.nombre}</span>
                      <small>{a.estado === "subiendo" ? "Lexia lo está leyendo…" : a.estado === "error" ? (a.nota || "No se pudo leer") : a.nota ? "Leído (ver nota)" : "Listo"}</small>
                    </span>
                    {a.estado === "subiendo" && <span className="adjunto__carga" />}
                    <button type="button" className="adjunto__quitar" aria-label={`Quitar ${a.nombre}`}
                      onClick={() => setAdjuntos((l) => l.filter((x) => x.id !== a.id))}>✕</button>
                  </div>
                ))}
              </div>
            )}
            <input ref={archivoRef} type="file" accept={ACEPTA} multiple hidden
              onChange={(e) => { agregarArchivos(e.target.files); e.target.value = ""; }} />
            <div className="redactor__fila">
              <button type="button" className="redactor__boton" onClick={() => archivoRef.current?.click()}
                title="Adjuntar foto, video, audio o documento" aria-label="Adjuntar archivo"
                disabled={ocupado || adjuntos.length >= MAX_ADJUNTOS}>
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M16.5 6.5v10.5a4.5 4.5 0 0 1-9 0V5a3 3 0 0 1 6 0v10.5a1.5 1.5 0 0 1-3 0V6.5H9v9a3 3 0 0 0 6 0V5a4.5 4.5 0 0 0-9 0v12a6 6 0 0 0 12 0V6.5h-1.5Z"/></svg>
              </button>
              <button type="button" className={`redactor__boton ${modoCaso ? "activo" : ""}`}
                onClick={() => setModoCaso((v) => !v)} title="Armar un caso" aria-label="Armar un caso" disabled={ocupado}>🗂️</button>
              <textarea
                ref={entradaRef}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    enviar();
                  }
                }}
                placeholder={modoCaso ? "Ej.: un conductor ebrio choca y se niega a la prueba de alcoholemia…" : "Pregúntale a Lexia sobre la ley…"}
                rows={1}
                maxLength={2000}
                aria-label="Mensaje para Lexia"
              />
              {puedeDictar && (
                <button type="button" className={`redactor__boton redactor__mic ${escuchando ? "grabando" : ""}`}
                  onClick={microfono} disabled={ocupado} title={escuchando ? "Terminar" : "Hablar con Lexia"}
                  aria-label={escuchando ? "Dejar de escuchar" : "Dictar por voz"}>
                  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                    <path fill="currentColor" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5.3-3a5.3 5.3 0 0 1-10.6 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-1.7Z" />
                  </svg>
                </button>
              )}
              <button type="submit" className="redactor__enviar" disabled={ocupado || subiendo || (texto.trim().length < 3 && !listos.length)} aria-label="Enviar">
                <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M3.4 20.4 21 12 3.4 3.6l-.01 6.53L15 12 3.39 13.87z" /></svg>
              </button>
            </div>
          </form>
        </main>
      </div>
    </>
  );
}
