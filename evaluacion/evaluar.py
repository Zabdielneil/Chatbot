"""Fase 6: evaluación del chatbot con el banco de preguntas.

Uso (desde la raíz del repo, con el .venv del motor activo):
    python evaluacion/evaluar.py                      # solo recuperación (no gasta API)
    python evaluacion/evaluar.py --respuestas         # además genera respuestas con el modelo de IA
    python evaluacion/evaluar.py --k 3 5 8            # valores de k a reportar

Recuperación (a nivel de artículo, sin contar los fragmentos "relacionados" que se agregan después):
    Precisión@k  = artículos esperados entre los k primeros artículos recuperados / k
    Recall@k     = artículos esperados recuperados en los k primeros / total de esperados
    MRR          = promedio de 1 / posición del primer artículo esperado
Se comparan las estrategias de segmentación (estructural vs. fija) y los modos de búsqueda
(semántico, léxico, híbrido). Las preguntas fuera de dominio no cuentan para estas métricas.

Detección de fuera de dominio (RF3): con la similitud máxima de FAISS se busca el umbral que mejor
separa las preguntas del Código de las de fuera de dominio, y se reporta la exactitud del umbral actual.

Respuestas (--respuestas):
    cita_correcta  = la respuesta cita al menos un artículo esperado y ninguno inventado (que no esté en el contexto)
    abstencion     = en fuera de dominio, la respuesta es la frase "No encontré..."; en dominio, no lo es
    tiempo         = segundos por consulta (RNF1: < 10 s)
La exactitud y la fidelidad al contexto se califican a mano (columnas vacías en el CSV) porque un
juez automático con el mismo modelo sería poco confiable para el informe.

Salidas en evaluacion/resultados/: reporte.md, recuperacion.csv y respuestas.csv
"""
import argparse
import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "motor" / "src"))
import rag  # noqa: E402

BANCO = RAIZ / "evaluacion" / "banco_preguntas.json"
SALIDA = RAIZ / "evaluacion" / "resultados"
ESTRATEGIAS = ["estructural", "fija"]
MODOS = ["semantico", "lexico", "hibrido"]


def articulos_rankeados(fuentes):
    """Lista de artículos únicos en el orden en que se recuperaron (sin los 'relacionados')."""
    vistos = []
    for f in fuentes:
        if f.get("origen") == "relacionado":
            continue
        if f["articulo"] not in vistos:
            vistos.append(f["articulo"])
    return vistos


def metricas(ranking, esperados, k):
    top = ranking[:k]
    aciertos = len(set(top) & set(esperados))
    rr = next((1 / (i + 1) for i, a in enumerate(ranking) if a in esperados), 0.0)
    return aciertos / k, aciertos / len(esperados), rr


def evaluar_recuperacion(preguntas, ks):
    """Devuelve filas por pregunta y el resumen por estrategia y modo."""
    filas, resumen, similitudes = [], [], {}
    kmax = max(ks)
    for estrategia in ESTRATEGIAS:
        try:
            motor = rag.Motor(estrategia)
        except SystemExit as e:
            print(f"  [{estrategia}] se omite: {e}")
            continue
        for modo in MODOS:
            acumulado = {k: [[], [], []] for k in ks}
            for p in preguntas:
                b = motor._buscar(p["pregunta"], kmax * 3, modo)
                if modo == "hibrido":
                    similitudes[(estrategia, p["id"])] = b["similitud_max"]
                if not p["articulos_esperados"]:
                    continue
                ranking = articulos_rankeados(b["fuentes"])
                fila = {"estrategia": estrategia, "modo": modo, "id": p["id"], "tipo": p["tipo"],
                        "esperados": " ".join(map(str, p["articulos_esperados"])),
                        "recuperados": " ".join(map(str, ranking[:kmax]))}
                for k in ks:
                    pk, rk, rr = metricas(ranking, p["articulos_esperados"], k)
                    acumulado[k][0].append(pk)
                    acumulado[k][1].append(rk)
                    acumulado[k][2].append(rr)
                    fila[f"P@{k}"], fila[f"R@{k}"] = round(pk, 3), round(rk, 3)
                fila["RR"] = round(rr, 3)
                filas.append(fila)
            for k in ks:
                p_, r_, rr_ = (statistics.mean(x) for x in acumulado[k])
                resumen.append({"estrategia": estrategia, "modo": modo, "k": k,
                                "P@k": p_, "R@k": r_, "MRR": rr_})
            print(f"  [{estrategia}/{modo}] " + " | ".join(
                f"P@{k}={statistics.mean(acumulado[k][0]):.3f} R@{k}={statistics.mean(acumulado[k][1]):.3f}"
                for k in ks) + f" | MRR={statistics.mean(acumulado[ks[0]][2]):.3f}")
    return filas, resumen, similitudes


def calibrar_umbral(preguntas, similitudes, estrategia="estructural"):
    puntos = [(similitudes[(estrategia, p["id"])], p["tipo"] != "fuera_de_dominio")
              for p in preguntas if (estrategia, p["id"]) in similitudes]
    if not puntos:
        return None

    def exactitud(u):
        return sum((s >= u) == en_dominio for s, en_dominio in puntos) / len(puntos)

    candidatos = sorted({round(s, 3) for s, _ in puntos})
    mejor = max(candidatos, key=exactitud)
    return {
        "actual": rag.UMBRAL_DOMINIO, "exactitud_actual": exactitud(rag.UMBRAL_DOMINIO),
        "mejor": mejor, "exactitud_mejor": exactitud(mejor),
        "dominio": [s for s, d in puntos if d], "fuera": [s for s, d in puntos if not d],
    }


RE_CITA = re.compile(r"Art(?:\.|ículo)\s*(\d{1,3})", re.IGNORECASE)


def evaluar_respuestas(preguntas):
    motor = rag.Motor("estructural")
    if motor.cliente_llm is None:
        print("  Falta LLM_API_KEY en el .env: no se pueden generar respuestas.")
        return []
    filas = []
    for p in preguntas:
        t0 = time.time()
        try:
            r = motor.preguntar(p["pregunta"])
            respuesta, error = r["respuesta"], ""
        except Exception as e:  # límite de la API, etc.
            r, respuesta, error = {"fuentes": []}, "", str(e)[:120]
        segundos = time.time() - t0
        citados = {int(n) for n in RE_CITA.findall(respuesta)}
        en_contexto = {f["articulo"] for f in r["fuentes"]}
        se_abstuvo = respuesta.strip().startswith("No encontré")
        fuera = p["tipo"] == "fuera_de_dominio"
        filas.append({
            "id": p["id"], "tipo": p["tipo"], "pregunta": p["pregunta"],
            "esperados": " ".join(map(str, p["articulos_esperados"])),
            "citados": " ".join(map(str, sorted(citados))),
            "cita_correcta": "" if fuera else int(bool(citados & set(p["articulos_esperados"]))
                                                  and citados <= en_contexto),
            "cita_inventada": int(bool(citados - en_contexto)),
            "abstencion_correcta": int(se_abstuvo == fuera),
            "segundos": round(segundos, 2),
            "exactitud_manual": "", "fidelidad_manual": "",
            "respuesta": respuesta.replace("\n", " "), "error": error,
        })
        print(f"  #{p['id']:>2} {segundos:4.1f}s cita={filas[-1]['cita_correcta']} "
              f"abst={filas[-1]['abstencion_correcta']} {error}")
        time.sleep(0.5)  # no saturar la capa gratuita del proveedor
    return filas


def escribir_csv(ruta, filas):
    if not filas:
        return
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, nargs="+", default=[3, 5])
    ap.add_argument("--respuestas", action="store_true", help="genera respuestas con el modelo de IA")
    args = ap.parse_args()

    banco = json.loads(BANCO.read_text(encoding="utf-8"))["preguntas"]
    n_dom = sum(1 for p in banco if p["articulos_esperados"])
    print(f"Banco: {len(banco)} preguntas ({n_dom} con artículos esperados, {len(banco) - n_dom} fuera de dominio)")
    SALIDA.mkdir(parents=True, exist_ok=True)

    print("\nRecuperación:")
    filas, resumen, similitudes = evaluar_recuperacion(banco, args.k)
    escribir_csv(SALIDA / "recuperacion.csv", filas)
    umbral = calibrar_umbral(banco, similitudes)

    md = ["# Reporte de evaluación\n",
          f"Banco: {len(banco)} preguntas ({n_dom} con artículos esperados, "
          f"{len(banco) - n_dom} fuera de dominio). Generado con `python evaluacion/evaluar.py`.\n",
          "## Recuperación (por artículo)\n",
          "| Estrategia | Modo | k | Precisión@k | Recall@k | MRR |", "|---|---|---|---|---|---|"]
    md += [f"| {r['estrategia']} | {r['modo']} | {r['k']} | {r['P@k']:.3f} | {r['R@k']:.3f} | {r['MRR']:.3f} |"
           for r in resumen]

    falladas = [f for f in filas if f["estrategia"] == "estructural" and f["modo"] == "hibrido" and f["RR"] == 0]
    md += ["\n### Preguntas sin ningún artículo esperado recuperado (estructural, híbrido)\n"]
    md += [f"- #{f['id']} ({f['tipo']}): esperaba {f['esperados']}, recuperó {f['recuperados']}" for f in falladas] \
        or ["- Ninguna"]

    if umbral:
        md += ["\n## Detección de preguntas fuera de dominio (similitud máxima FAISS)\n",
               f"- Umbral actual (`UMBRAL_DOMINIO`): {umbral['actual']} → exactitud {umbral['exactitud_actual']:.1%}",
               f"- Mejor umbral en este banco: {umbral['mejor']} → exactitud {umbral['exactitud_mejor']:.1%}",
               f"- Similitud en preguntas del Código: mín {min(umbral['dominio']):.3f}, "
               f"mediana {statistics.median(umbral['dominio']):.3f}",
               f"- Similitud en preguntas fuera de dominio: máx {max(umbral['fuera']):.3f}, "
               f"mediana {statistics.median(umbral['fuera']):.3f}"]
        print(f"\nUmbral fuera de dominio: actual {umbral['actual']} ({umbral['exactitud_actual']:.1%}), "
              f"mejor {umbral['mejor']} ({umbral['exactitud_mejor']:.1%})")

    if args.respuestas:
        print("\nRespuestas con el modelo de IA:")
        resp = evaluar_respuestas(banco)
        escribir_csv(SALIDA / "respuestas.csv", resp)
        if resp:
            dom = [r for r in resp if r["cita_correcta"] != ""]
            tiempos = [r["segundos"] for r in resp if not r["error"]]
            md += ["\n## Respuestas\n",
                   f"- Cita correcta (dominio): {statistics.mean(r['cita_correcta'] for r in dom):.1%}",
                   f"- Respuestas con algún artículo citado que no estaba en el contexto: "
                   f"{sum(r['cita_inventada'] for r in resp)}",
                   f"- Abstención correcta (todas): {statistics.mean(r['abstencion_correcta'] for r in resp):.1%}",
                   f"- Tiempo por consulta: mediana {statistics.median(tiempos):.1f} s, máximo {max(tiempos):.1f} s "
                   f"(RNF1 < 10 s)" if tiempos else "- Sin tiempos válidos",
                   "- Exactitud y fidelidad: calificar a mano en `respuestas.csv`."]

    (SALIDA / "reporte.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nReporte en {SALIDA / 'reporte.md'}")


if __name__ == "__main__":
    main()
