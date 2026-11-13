// Arranca el backend público del chatbot. Toda la lógica (rutas, CORS, helmet, límite de
// peticiones, validaciones) está en app.js; las pruebas (test/app.test.js) importan la misma app.
// Uso:  cd backend && npm install && npm run dev
import dotenv from "dotenv";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { crearApp } from "./app.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.join(__dirname, "..", ".env") }); // .env en la raíz del repo

const PUERTO = Number(process.env.PUERTO_BACKEND) || 3001;
const MOTOR_URL = process.env.MOTOR_URL || "http://localhost:8000";
const ORIGENES = (process.env.ORIGENES_PERMITIDOS || "http://localhost:5173")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);
const DIR_PENDIENTES = path.join(__dirname, "..", "motor", "data", "pendientes");
fs.mkdirSync(DIR_PENDIENTES, { recursive: true });

const app = crearApp({
  motorUrl: MOTOR_URL,
  origenes: ORIGENES,
  dirPendientes: DIR_PENDIENTES,
  limiteChatPorMinuto: Number(process.env.LIMITE_CHAT_POR_MINUTO) || 20,
});

app.listen(PUERTO, () => {
  console.log(`Backend en http://localhost:${PUERTO}  →  motor en ${MOTOR_URL}`);
  console.log(`Orígenes permitidos: ${ORIGENES.join(", ")}`);
});
