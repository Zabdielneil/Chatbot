// Aplicación Express del backend público. server.js la levanta; las pruebas la importan directamente.
//   POST /api/chat        → valida la pregunta y la reenvía al motor Python (POST /query)
//   POST /upload_pdf/     → guarda un PDF en motor/data/pendientes SIN reindexar (RF4)
//   GET  /api/pendientes  → lista los PDF que esperan ser indexados
//   GET  /api/health      → estado del backend y del motor

import express from "express";
import cors from "cors";
import helmet from "helmet";
import multer from "multer";
import rateLimit from "express-rate-limit";
import fs from "node:fs";
import path from "node:path";

export const AVISO = "Herramienta informativa. No sustituye la asesoría de un abogado.";
const K_MIN = 1;
const K_MAX = 15; // el motor rechaza valores mayores
const PREGUNTA_MIN = 3;
const PREGUNTA_MAX = 500;
const MODOS = ["hibrido", "semantico", "lexico"]; // modos de búsqueda del motor (rag.py)

class ErrorHttp extends Error {
  constructor(status, mensaje) {
    super(mensaje);
    this.status = status;
  }
}

// FastAPI devuelve detail como texto (HTTPException) o como lista de errores de validación (422)
function mensajeDelMotor(datos) {
  const d = datos?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e.msg).join("; ");
  return "Error en el motor";
}

export function crearApp({
  motorUrl = "http://localhost:8000",
  origenes = ["http://localhost:5173"],
  dirPendientes,
  timeoutMotorMs = 30000,
  limiteChatPorMinuto = 20,
  limiteSubidasPorHora = 10,
} = {}) {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1); // para que el rate limit vea la IP real detrás de un proxy en el despliegue
  app.use(helmet());
  app.use(express.json({ limit: "100kb" }));

  // RNF3: solo los orígenes configurados pueden llamar a la API desde un navegador.
  // Las peticiones sin Origin (curl, Postman, el script de evaluación) se permiten.
  app.use(
    cors({
      origin(origin, cb) {
        if (!origin || origenes.includes(origin)) return cb(null, true);
        cb(new ErrorHttp(403, `Origen no permitido por CORS: ${origin}`));
      },
      methods: ["GET", "POST"],
    })
  );

  // Registro de peticiones: método, ruta, estado y tiempo. No se guarda el texto de las preguntas
  // porque puede contener datos personales (Ley 1581 de 2012).
  app.use((req, res, next) => {
    const t0 = Date.now();
    res.on("finish", () => {
      if (process.env.NODE_ENV !== "test") {
        console.log(`${req.method} ${req.path} ${res.statusCode} ${Date.now() - t0}ms`);
      }
    });
    next();
  });

  const limitar = (max, ventanaMs, mensaje) =>
    rateLimit({
      windowMs: ventanaMs,
      limit: max,
      standardHeaders: "draft-7",
      legacyHeaders: false,
      handler: (_req, res) => res.status(429).json({ error: mensaje }),
    });

  // ---------- chat ----------
  app.post(
    "/api/chat",
    limitar(limiteChatPorMinuto, 60_000, "Demasiadas preguntas seguidas. Espera un minuto e intenta de nuevo."),
    async (req, res, next) => {
      try {
        const pregunta = typeof req.body?.pregunta === "string" ? req.body.pregunta.trim() : "";
        if (pregunta.length < PREGUNTA_MIN) {
          throw new ErrorHttp(400, `Escribe una pregunta de al menos ${PREGUNTA_MIN} caracteres.`);
        }
        if (pregunta.length > PREGUNTA_MAX) {
          throw new ErrorHttp(400, `La pregunta no puede pasar de ${PREGUNTA_MAX} caracteres.`);
        }
        // k y modo son opcionales: si no llegan, el motor usa sus valores por defecto (k=8, híbrido)
        const consulta = { pregunta };
        if (req.body?.k !== undefined) {
          const k = Number(req.body.k);
          if (!Number.isInteger(k) || k < K_MIN || k > K_MAX) {
            throw new ErrorHttp(400, `k debe ser un entero entre ${K_MIN} y ${K_MAX}.`);
          }
          consulta.k = k;
        }
        if (req.body?.modo !== undefined) {
          if (!MODOS.includes(req.body.modo)) {
            throw new ErrorHttp(400, `modo debe ser uno de: ${MODOS.join(", ")}.`);
          }
          consulta.modo = req.body.modo;
        }

        let r;
        try {
          r = await fetch(`${motorUrl}/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(consulta),
            signal: AbortSignal.timeout(timeoutMotorMs),
          });
        } catch (e) {
          if (e.name === "TimeoutError") {
            throw new ErrorHttp(504, "El motor tardó demasiado en responder. Intenta de nuevo.");
          }
          throw new ErrorHttp(503, `No se pudo conectar con el motor en ${motorUrl}.`);
        }

        const datos = await r.json().catch(() => null);
        if (!r.ok) {
          // 502 cuando falla el LLM, 422 si el motor rechazó la entrada, etc.
          throw new ErrorHttp(r.status >= 500 ? 502 : r.status, mensajeDelMotor(datos));
        }
        if (!datos || typeof datos.respuesta !== "string") {
          throw new ErrorHttp(502, "El motor devolvió una respuesta con formato inesperado.");
        }
        res.json({ ...datos, aviso: AVISO });
      } catch (e) {
        next(e);
      }
    }
  );

  // ---------- carga de PDF (RF4: no regenera los embeddings) ----------
  fs.mkdirSync(dirPendientes, { recursive: true });
  const subir = multer({
    storage: multer.diskStorage({
      destination: dirPendientes,
      filename: (_req, file, cb) =>
        cb(null, `${Date.now()}_${path.basename(file.originalname).replace(/[^\w.\-]/g, "_")}`),
    }),
    limits: { fileSize: 20 * 1024 * 1024, files: 1 },
    fileFilter: (_req, file, cb) =>
      file.mimetype === "application/pdf" && /\.pdf$/i.test(file.originalname)
        ? cb(null, true)
        : cb(new ErrorHttp(415, "Solo se aceptan archivos PDF.")),
  });

  app.post(
    "/upload_pdf/",
    limitar(limiteSubidasPorHora, 3_600_000, "Demasiadas cargas de archivos. Intenta más tarde."),
    subir.single("archivo"),
    async (req, res, next) => {
      try {
        if (!req.file) throw new ErrorHttp(400, "Envíen el PDF en el campo 'archivo'.");
        // el tipo MIME lo declara el cliente; comprobamos la firma real del archivo (%PDF-)
        const fh = await fs.promises.open(req.file.path, "r");
        const cabecera = Buffer.alloc(5);
        await fh.read(cabecera, 0, 5, 0);
        await fh.close();
        if (cabecera.toString("latin1") !== "%PDF-") {
          await fs.promises.unlink(req.file.path);
          throw new ErrorHttp(415, "El archivo no es un PDF válido.");
        }
        res.status(201).json({
          mensaje: "PDF guardado. Para incluirlo en el chatbot hay que reindexar manualmente.",
          archivo: req.file.filename,
          tamano_bytes: req.file.size,
        });
      } catch (e) {
        next(e);
      }
    }
  );

  app.get("/api/pendientes", async (_req, res, next) => {
    try {
      const nombres = (await fs.promises.readdir(dirPendientes)).filter((n) => /\.pdf$/i.test(n));
      const archivos = await Promise.all(
        nombres.map(async (n) => {
          const st = await fs.promises.stat(path.join(dirPendientes, n));
          return { archivo: n, tamano_bytes: st.size, subido: st.mtime.toISOString() };
        })
      );
      res.json({ total: archivos.length, archivos });
    } catch (e) {
      next(e);
    }
  });

  // ---------- estado ----------
  app.get("/api/health", async (_req, res) => {
    let motor = "sin conexión";
    try {
      const r = await fetch(`${motorUrl}/health`, { signal: AbortSignal.timeout(3000) });
      motor = await r.json();
    } catch {}
    res.json({ backend: "ok", motor });
  });

  // ---------- rutas desconocidas y errores ----------
  app.use((req, res) => res.status(404).json({ error: `No existe la ruta ${req.method} ${req.path}` }));

  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    let status = err.status || 500;
    let mensaje = err.message;
    if (err instanceof multer.MulterError) {
      status = err.code === "LIMIT_FILE_SIZE" ? 413 : 400;
      mensaje = err.code === "LIMIT_FILE_SIZE" ? "El PDF no puede pasar de 20 MB." : err.message;
    } else if (err.type === "entity.parse.failed") {
      status = 400;
      mensaje = "El cuerpo de la petición no es un JSON válido.";
    } else if (err.type === "entity.too.large") {
      status = 413;
      mensaje = "La petición es demasiado grande.";
    } else if (status === 500) {
      console.error(err);
      mensaje = "Error interno del servidor.";
    }
    res.status(status).json({ error: mensaje });
  });

  return app;
}
