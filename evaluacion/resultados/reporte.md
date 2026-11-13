# Reporte de evaluación

Banco: 64 preguntas (54 con artículos esperados, 10 fuera de dominio). Generado con `python evaluacion/evaluar.py`.

## Recuperación (por artículo)

| Estrategia | Modo | k | Precisión@k | Recall@k | MRR |
|---|---|---|---|---|---|
| estructural | semantico | 3 | 0.296 | 0.748 | 0.643 |
| estructural | semantico | 5 | 0.193 | 0.793 | 0.643 |
| estructural | lexico | 3 | 0.284 | 0.748 | 0.661 |
| estructural | lexico | 5 | 0.185 | 0.804 | 0.661 |
| estructural | hibrido | 3 | 0.296 | 0.767 | 0.726 |
| estructural | hibrido | 5 | 0.193 | 0.832 | 0.726 |
| fija | semantico | 3 | 0.265 | 0.679 | 0.676 |
| fija | semantico | 5 | 0.185 | 0.772 | 0.676 |
| fija | lexico | 3 | 0.259 | 0.694 | 0.668 |
| fija | lexico | 5 | 0.181 | 0.787 | 0.668 |
| fija | hibrido | 3 | 0.290 | 0.748 | 0.725 |
| fija | hibrido | 5 | 0.185 | 0.772 | 0.725 |

### Preguntas sin ningún artículo esperado recuperado (estructural, híbrido)

- #4 (dominio): esperaba 222 210, recuperó 219 218 154 228 223
- #19 (coloquial): esperaba 27, recuperó 36 135 155 33 140
- #22 (dominio): esperaba 35, recuperó 210 168 198 183 163

## Detección de preguntas fuera de dominio (similitud máxima FAISS)

- Umbral actual (`UMBRAL_DOMINIO`): 0.37 → exactitud 87.5%
- Mejor umbral en este banco: 0.433 → exactitud 89.1%
- Similitud en preguntas del Código: mín 0.378, mediana 0.673
- Similitud en preguntas fuera de dominio: máx 0.574, mediana 0.468
