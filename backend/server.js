// Backend público del chatbot (Node.js + Express).
// - /api/chat       → reenvía la pregunta al motor Python (FastAPI) y devuelve respuesta + fuentes
// - /upload_pdf/    → guarda un PDF nuevo en motor/data/pendientes SIN reindexar (RF4)
// - /api/health     → estado del backend y del motor
// Uso:  cd backend && npm install && npm run dev

import express from "express";
import cors from "cors";
import multer from "multer";
import dotenv from "dotenv";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.join(__dirname, "..", ".env") }); // .env en la raíz del repo

const PUERTO = process.env.PUERTO_BACKEND || 3001;
const MOTOR_URL = process.env.MOTOR_URL || "http://localhost:8000";
const ORIGENES = (process.env.ORIGENES_PERMITIDOS || "http://localhost:5173")
  .split(",")
  .map((o) => o.trim());
const DIR_PENDIENTES = path.join(__dirname, "..", "motor", "data", "pendientes");

const app = express();
app.use(express.json({ limit: "100kb" }));

// RNF3: solo los orígenes del .env pueden llamar a la API desde el navegador
app.use(
  cors({
    origin(origin, cb) {
      if (!origin || ORIGENES.includes(origin)) return cb(null, true);
      cb(new Error(`Origen no permitido por CORS: ${origin}`));
    },
  })
);

// ---------- chat ----------
app.post("/api/chat", async (req, res) => {
  const pregunta = (req.body?.pregunta || "").trim();
    const k = Number(req.body?.k) || 8;
  if (pregunta.length < 3) {
    return res.status(400).json({ error: "Escribe una pregunta de al menos 3 caracteres." });
  }
  try {
    const r = await fetch(`${MOTOR_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta, k }),
      signal: AbortSignal.timeout(30000),
    });
    const datos = await r.json();
    if (!r.ok) return res.status(r.status).json({ error: datos.detail || "Error en el motor" });
    res.json({
      ...datos,
      aviso: "Herramienta informativa. No sustituye la asesoría de un abogado.",
    });
  } catch (e) {
    res.status(503).json({ error: `No se pudo conectar con el motor en ${MOTOR_URL}: ${e.message}` });
  }
});

// ---------- carga de PDF (RF4: no regenera embeddings automáticamente) ----------
fs.mkdirSync(DIR_PENDIENTES, { recursive: true });
const subir = multer({
  storage: multer.diskStorage({
    destination: DIR_PENDIENTES,
    filename: (_req, file, cb) =>
      cb(null, `${Date.now()}_${file.originalname.replace(/[^\w.\-]/g, "_")}`),
  }),
  limits: { fileSize: 20 * 1024 * 1024 },
  fileFilter: (_req, file, cb) =>
    file.mimetype === "application/pdf" ? cb(null, true) : cb(new Error("Solo se aceptan archivos PDF")),
});

app.post("/upload_pdf/", subir.single("archivo"), (req, res) => {
  if (!req.file) return res.status(400).json({ error: "Envíen el PDF en el campo 'archivo'." });
  res.status(201).json({
    mensaje: "PDF guardado. Para incluirlo en el chatbot hay que reindexar manualmente.",
    archivo: req.file.filename,
    tamano_bytes: req.file.size,
  });
});

// ---------- estado ----------
app.get("/api/health", async (_req, res) => {
  let motor = "sin conexión";
  try {
    const r = await fetch(`${MOTOR_URL}/health`, { signal: AbortSignal.timeout(3000) });
    motor = await r.json();
  } catch {}
  res.json({ backend: "ok", motor });
});

// errores (CORS, multer, etc.)
app.use((err, _req, res, _next) => res.status(400).json({ error: err.message }));

app.listen(PUERTO, () => {
  console.log(`Backend en http://localhost:${PUERTO}  →  motor en ${MOTOR_URL}`);
  console.log(`Orígenes permitidos: ${ORIGENES.join(", ")}`);
});
