# Reporte de evaluación

Banco: 68 preguntas (58 con artículos esperados, 10 fuera de dominio). Generado con `python evaluacion/evaluar.py`.

## Recuperación (por artículo)

| Estrategia | Modo | k | Precisión@k | Recall@k | MRR |
|---|---|---|---|---|---|
| estructural | semantico | 3 | 0.276 | 0.667 | 0.641 |
| estructural | semantico | 5 | 0.193 | 0.756 | 0.641 |
| estructural | lexico | 3 | 0.282 | 0.705 | 0.688 |
| estructural | lexico | 5 | 0.179 | 0.757 | 0.688 |
| estructural | hibrido | 3 | 0.299 | 0.740 | 0.715 |
| estructural | hibrido | 5 | 0.197 | 0.803 | 0.715 |
| fija | semantico | 3 | 0.259 | 0.624 | 0.627 |
| fija | semantico | 5 | 0.183 | 0.726 | 0.627 |
| fija | lexico | 3 | 0.259 | 0.655 | 0.641 |
| fija | lexico | 5 | 0.186 | 0.776 | 0.641 |
| fija | hibrido | 3 | 0.287 | 0.705 | 0.679 |
| fija | hibrido | 5 | 0.186 | 0.744 | 0.679 |

### Preguntas sin ningún artículo esperado recuperado (estructural, híbrido)

- #4 (dominio): esperaba 222 210, recuperó 219 769:135 769:147 218 769:137
- #12 (dominio): esperaba 180, recuperó 146 124 134 103 110
- #19 (coloquial): esperaba 27, recuperó 769:120 769:79 36 769:127 140
- #22 (dominio): esperaba 35, recuperó 159 184 155 157 183

## Detección de preguntas fuera de dominio (similitud máxima FAISS)

- Umbral actual (`UMBRAL_DOMINIO`): 0.37 → exactitud 88.2%
- Mejor umbral en este banco: 0.364 → exactitud 88.2%
- Similitud en preguntas del Código: mín 0.411, mediana 0.675
- Similitud en preguntas fuera de dominio: máx 0.692, mediana 0.549
