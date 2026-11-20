// Avatar de Lexia con estados animados:
//   reposo      halo suave que respira
//   pensando    anillo de luz girando (está buscando / leyendo la ley)
//   hablando    pulso cálido al entregar la respuesta
export default function Avatar({ estado = "reposo", tamano = 44, conHalo = true }) {
  return (
    <div
      className={`avatar avatar--${estado} ${conHalo ? "avatar--halo" : ""}`}
      style={{ "--tam": `${tamano}px` }}
      aria-hidden="true"
    >
      <div className="avatar__anillo" />
      <img src="/lexia.png" alt="" className="avatar__img" draggable="false" />
      {estado !== "reposo" && <span className="avatar__chispa" />}
    </div>
  );
}
