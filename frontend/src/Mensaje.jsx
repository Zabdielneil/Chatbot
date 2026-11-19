import { useMemo, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import Avatar from "./Avatar.jsx";
import { leer, callar, puedeLeer } from "./voz.js";

marked.setOptions({ breaks: true, gfm: true });

// Citas como "(Ley 1801, Art. 35, num. 3)", "Art. 140", "Artículo 131" → chips clicables
const RE_CITA = /((?:Ley\s+(?:1801|769)(?:\s+de\s+\d{4})?,\s*)?Art(?:\.|ículo)\s*\d{1,3}[A-Z]?(?:\s*,\s*(?:num\.|numeral|par\.|parágrafo|lit\.|literal)\s*[\w.°º]+)?)/g;

function htmlDeRespuesta(texto) {
  // espacios finos y guiones no separables que algunos modelos usan y la fuente dibuja sin ancho
  const normal = (texto || "").replace(/[     ]/g, " ").replace(/‑/g, "-");
  const html = DOMPurify.sanitize(marked.parse(normal));
  // solo se reemplaza en el texto, no dentro de etiquetas
  return html.replace(/>([^<]+)</g, (_, t) =>
    `>${t.replace(RE_CITA, (c) => {
      const art = (c.match(/Art(?:\.|ículo)\s*(\d{1,3}[A-Z]?)/) || [])[1];
      const ley = /769/.test(c) ? "769" : /1801/.test(c) ? "1801" : "";
      return `<button type="button" class="cita" data-art="${art}" data-ley="${ley}">${c}</button>`;
    })}<`
  );
}

const hora = (t) => (t ? new Date(t).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" }) : "");

function Fuente({ f, abierta, onToggle }) {
  const v = f.vigencia || "vigente";
  const clase = v === "vigente" ? "ok" : v.startsWith("inexequible") || v === "derogado" ? "mal" : "ojo";
  const transito = (f.norma || "").includes("769");
  return (
    <li className={`fuente ${abierta ? "fuente--abierta" : ""}`}>
      <button className="fuente__cabecera" onClick={onToggle} aria-expanded={abierta}>
        <span className={`fuente__ley ${transito ? "fuente__ley--transito" : ""}`}>{transito ? "Tránsito" : "Policía"}</span>
        <span className="fuente__ref">{f.ref.replace(/^Ley 769 de 2002, /, "")}</span>
        <span className="fuente__epigrafe">{f.epigrafe}</span>
        <span className={`vigencia vigencia--${clase}`}>{v}</span>
      </button>
      {abierta && (
        <div className="fuente__cuerpo">
          <blockquote>{f.texto}</blockquote>
          {f.medida_correctiva && <p className="fuente__medida">⚖️ {f.medida_correctiva}</p>}
        </div>
      )}
    </li>
  );
}

export default function Mensaje({ mensaje, onReintentar, enCurso }) {
  const [verFuentes, setVerFuentes] = useState(false);
  const [verPasos, setVerPasos] = useState(false);
  const [abiertas, setAbiertas] = useState(() => new Set());
  const [copiado, setCopiado] = useState(false);
  const [hablando, setHablando] = useState(false);
  const html = useMemo(() => (mensaje.rol === "lexia" ? htmlDeRespuesta(mensaje.texto) : ""), [mensaje]);

  if (mensaje.rol === "usuario") {
    return (
      <div className="fila fila--usuario">
        <div className="burbuja burbuja--usuario">
          <p>{mensaje.texto}</p>
          <span className="burbuja__hora">{hora(mensaje.t)} ✓✓</span>
        </div>
      </div>
    );
  }

  if (mensaje.rol === "error") {
    return (
      <div className="fila fila--lexia">
        <Avatar tamano={34} conHalo={false} />
        <div className="burbuja burbuja--error">
          <p>😕 {mensaje.texto}</p>
          <button className="boton-suave" onClick={onReintentar}>Reintentar</button>
        </div>
      </div>
    );
  }

  const fuentes = mensaje.fuentes || [];
  const pasos = mensaje.pasos || [];
  const esCaso = /^\s*##\s*🗂️/.test(mensaje.texto || "");

  function abrirCita(e) {
    const boton = e.target.closest(".cita");
    if (!boton) return;
    const i = fuentes.findIndex(
      (f) => String(f.articulo) === boton.dataset.art &&
        (!boton.dataset.ley || (f.norma || "").includes(boton.dataset.ley))
    );
    if (i < 0) return;
    setVerFuentes(true);
    setAbiertas((s) => new Set(s).add(i));
  }

  function copiar() {
    navigator.clipboard?.writeText(mensaje.texto).then(() => {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1500);
    });
  }

  return (
    <div className="fila fila--lexia">
      <Avatar tamano={34} conHalo={false} />
      <div className={`burbuja burbuja--lexia ${esCaso ? "burbuja--caso" : ""}`}>
        {pasos.length > 0 && (
          <button className="pasos__toggle" onClick={() => setVerPasos((v) => !v)} aria-expanded={verPasos}>
            <span className="pasos__icono">✦</span> Lexia consultó la ley en {pasos.length} pasos
            <span className="chevron">{verPasos ? "▴" : "▾"}</span>
          </button>
        )}
        {verPasos && (
          <ol className="pasos">
            {pasos.map((p, i) => <li key={i}>{p}</li>)}
          </ol>
        )}

        <div className="md" onClick={abrirCita} dangerouslySetInnerHTML={{ __html: html }} />

        {fuentes.length > 0 && (
          <div className="fuentes">
            <button className="fuentes__toggle" onClick={() => setVerFuentes((v) => !v)} aria-expanded={verFuentes}>
              📖 {fuentes.length} {fuentes.length === 1 ? "fuente consultada" : "fuentes consultadas"}
              <span className="chevron">{verFuentes ? "▴" : "▾"}</span>
            </button>
            {verFuentes && (
              <ul>
                {fuentes.map((f, i) => (
                  <Fuente key={i} f={f} abierta={abiertas.has(i)}
                    onToggle={() => setAbiertas((s) => {
                      const n = new Set(s);
                      n.has(i) ? n.delete(i) : n.add(i);
                      return n;
                    })} />
                ))}
              </ul>
            )}
          </div>
        )}

        {!enCurso && (
          <div className="burbuja__pie">
            <span className="acciones">
              <button className="accion" onClick={copiar} title="Copiar respuesta">{copiado ? "✓ Copiado" : "⧉ Copiar"}</button>
              {puedeLeer && (
                <button className={`accion ${hablando ? "accion--activa" : ""}`} title="Escuchar respuesta"
                  onClick={() => {
                    if (hablando) { callar(); setHablando(false); return; }
                    setHablando(true);
                    leer(mensaje.texto, () => setHablando(false));
                  }}>
                  {hablando ? "■ Detener" : "🔊 Escuchar"}
                </button>
              )}
            </span>
            <span className="burbuja__hora">
              {mensaje.tiempo_ms != null && `${(mensaje.tiempo_ms / 1000).toFixed(1)} s · `}{hora(mensaje.t)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
