import { useState } from "react";

// Detecta citas como "(Art. 140, num. 4)", "Art. 180, par. 1" o "artículo 35"
const RE_CITA = /(\(?\b(?:Art\.|Artículo|artículo)\s*\d{1,3}(?:\s*,\s*(?:num\.|numeral|par\.|parágrafo)\s*[\w°º]+)?\)?)/g;

function numeroArticulo(cita) {
  const m = cita.match(/\d{1,3}/);
  return m ? Number(m[0]) : null;
}

// Pinta la respuesta resaltando las citas; al hacer clic en una cita se abre esa fuente.
function TextoConCitas({ texto, onCita }) {
  return texto.split("\n").map((parrafo, i) => (
    <p key={i}>
      {parrafo.split(RE_CITA).map((trozo, j) =>
        j % 2 === 1 ? (
          <button key={j} className="cita" onClick={() => onCita(numeroArticulo(trozo))} title="Ver la fuente">
            {trozo}
          </button>
        ) : (
          trozo
        )
      )}
    </p>
  ));
}

function Fuente({ f, abierta, onToggle }) {
  const claseVigencia = f.vigencia === "vigente" ? "ok" : f.vigencia === "derogado" ? "mal" : "ojo";
  return (
    <li className={`fuente ${abierta ? "abierta" : ""}`}>
      <button className="fuente-cabecera" onClick={onToggle} aria-expanded={abierta}>
        <span className="fuente-ref">{f.ref}</span>
        <span className="fuente-epigrafe">{f.epigrafe}</span>
        <span className={`vigencia ${claseVigencia}`}>{f.vigencia}</span>
        <span className="puntaje" title="Similitud con la pregunta (0 a 1)">
          {Math.round(f.puntaje * 100)}%
        </span>
      </button>
      {abierta && <blockquote className="fuente-texto">{f.texto}</blockquote>}
    </li>
  );
}

export default function Mensaje({ mensaje, onReintentar }) {
  const [verFuentes, setVerFuentes] = useState(false);
  const [abiertas, setAbiertas] = useState(new Set());

  if (mensaje.rol === "usuario") {
    return (
      <div className="mensaje usuario">
        <div className="burbuja">{mensaje.texto}</div>
      </div>
    );
  }

  if (mensaje.rol === "error") {
    return (
      <div className="mensaje bot">
        <div className="burbuja error">
          <p>{mensaje.texto}</p>
          <button className="boton-secundario" onClick={onReintentar}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const fuentes = mensaje.fuentes || [];

  function alternar(i) {
    setAbiertas((s) => {
      const n = new Set(s);
      n.has(i) ? n.delete(i) : n.add(i);
      return n;
    });
  }

  function abrirCita(articulo) {
    const i = fuentes.findIndex((f) => f.articulo === articulo);
    if (i < 0) return;
    setVerFuentes(true);
    setAbiertas((s) => new Set(s).add(i));
  }

  return (
    <div className="mensaje bot">
      <div className="burbuja">
        <TextoConCitas texto={mensaje.texto} onCita={abrirCita} />

        {fuentes.length > 0 && (
          <div className="fuentes">
            <button className="ver-fuentes" onClick={() => setVerFuentes((v) => !v)} aria-expanded={verFuentes}>
              {verFuentes ? "▾" : "▸"} Fragmentos consultados ({fuentes.length})
            </button>
            {verFuentes && (
              <ul>
                {fuentes.map((f, i) => (
                  <Fuente key={i} f={f} abierta={abiertas.has(i)} onToggle={() => alternar(i)} />
                ))}
              </ul>
            )}
          </div>
        )}
        {mensaje.tiempo_ms != null && (
          <div className="meta">{(mensaje.tiempo_ms / 1000).toFixed(1)} s</div>
        )}
      </div>
    </div>
  );
}
