// Pruebas del backend con un motor Python falso (no hace falta FAISS ni modelo de IA).
// Uso: cd backend && npm test
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { crearApp, AVISO } from "../app.js";

process.env.NODE_ENV = "test";

const ORIGEN_OK = "http://localhost:5173";
let motor, servidor, api, dirPendientes;
let modoMotor = "ok"; // ok | error_llm | validacion | lento

function escuchar(srv) {
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok(`http://127.0.0.1:${srv.address().port}`)));
}

before(async () => {
  motor = http.createServer((req, res) => {
    let cuerpo = "";
    req.on("data", (c) => (cuerpo += c));
    req.on("end", () => {
      res.setHeader("Content-Type", "application/json");
      if (req.url === "/health") return res.end(JSON.stringify({ estado: "ok" }));
      if (modoMotor === "error_llm") {
        res.statusCode = 502;
        return res.end(JSON.stringify({ detail: "Error llamando al modelo de IA: clave inválida" }));
      }
      if (modoMotor === "validacion") {
        res.statusCode = 422;
        return res.end(JSON.stringify({ detail: [{ msg: "campo inválido" }, { msg: "otro error" }] }));
      }
      const { pregunta, k, modo } = JSON.parse(cuerpo);
      const responder = () =>
        res.end(JSON.stringify({ pregunta, respuesta: `ok k=${k} modo=${modo}`, fuentes: [], tiempo_ms: 1 }));
      modoMotor === "lento" ? setTimeout(responder, 300) : responder();
    });
  });
  const motorUrl = await escuchar(motor);

  dirPendientes = fs.mkdtempSync(path.join(os.tmpdir(), "pendientes-"));
  const app = crearApp({
    motorUrl,
    origenes: [ORIGEN_OK],
    dirPendientes,
    timeoutMotorMs: 150,
    limiteChatPorMinuto: 1000,
  });
  servidor = http.createServer(app);
  api = await escuchar(servidor);
});

after(() => {
  motor.close();
  servidor.close();
  fs.rmSync(dirPendientes, { recursive: true, force: true });
});

const chat = (body, headers = {}) =>
  fetch(`${api}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });

// ---------- /api/chat ----------
test("reenvía la pregunta al motor y agrega el aviso legal", async () => {
  modoMotor = "ok";
  const r = await chat({ pregunta: "  ¿Qué es un comparendo?  ", k: 3 });
  assert.equal(r.status, 200);
  const d = await r.json();
  assert.equal(d.pregunta, "¿Qué es un comparendo?");
  assert.equal(d.respuesta, "ok k=3 modo=undefined");
  assert.equal(d.aviso, AVISO);
});

test("sin k ni modo deja que el motor use sus valores por defecto", async () => {
  modoMotor = "ok";
  const d = await (await chat({ pregunta: "¿Qué es un comparendo?" })).json();
  assert.equal(d.respuesta, "ok k=undefined modo=undefined");
});

test("reenvía el modo de búsqueda y rechaza modos inválidos", async () => {
  modoMotor = "ok";
  const d = await (await chat({ pregunta: "¿Qué es un comparendo?", modo: "lexico" })).json();
  assert.equal(d.respuesta, "ok k=undefined modo=lexico");
  assert.equal((await chat({ pregunta: "¿Qué es un comparendo?", modo: "magico" })).status, 400);
});

test("rechaza preguntas vacías, muy largas o que no son texto", async () => {
  for (const body of [{ pregunta: "  " }, { pregunta: "a".repeat(501) }, { pregunta: 123 }, {}]) {
    const r = await chat(body);
    assert.equal(r.status, 400, JSON.stringify(body));
  }
});

test("rechaza k fuera de rango", async () => {
  for (const k of [0, 16, 2.5, "abc"]) {
    assert.equal((await chat({ pregunta: "¿Qué es un comparendo?", k })).status, 400, `k=${k}`);
  }
});

test("JSON mal formado da 400 con mensaje claro", async () => {
  const r = await chat("{no es json");
  assert.equal(r.status, 400);
  assert.match((await r.json()).error, /JSON/);
});

test("error del LLM en el motor se devuelve como 502 con el detalle", async () => {
  modoMotor = "error_llm";
  const r = await chat({ pregunta: "¿Qué es un comparendo?" });
  assert.equal(r.status, 502);
  assert.match((await r.json()).error, /clave inválida/);
});

test("errores de validación del motor (lista) se convierten en texto", async () => {
  modoMotor = "validacion";
  const r = await chat({ pregunta: "¿Qué es un comparendo?" });
  assert.equal(r.status, 422);
  assert.equal((await r.json()).error, "campo inválido; otro error");
});

test("motor lento da 504", async () => {
  modoMotor = "lento";
  const r = await chat({ pregunta: "¿Qué es un comparendo?" });
  assert.equal(r.status, 504);
});

test("motor apagado da 503", async () => {
  const app = crearApp({ motorUrl: "http://127.0.0.1:1", dirPendientes, limiteChatPorMinuto: 1000 });
  const srv = http.createServer(app);
  const url = await escuchar(srv);
  const r = await fetch(`${url}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta: "¿Qué es un comparendo?" }),
  });
  srv.close();
  assert.equal(r.status, 503);
});

// ---------- CORS (RNF3) ----------
test("CORS permite el origen configurado", async () => {
  modoMotor = "ok";
  const r = await chat({ pregunta: "¿Qué es un comparendo?" }, { Origin: ORIGEN_OK });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("access-control-allow-origin"), ORIGEN_OK);
});

test("CORS bloquea otros orígenes con 403", async () => {
  const r = await chat({ pregunta: "¿Qué es un comparendo?" }, { Origin: "https://sitio-malo.com" });
  assert.equal(r.status, 403);
});

// ---------- /upload_pdf/ (RF4) ----------
const subir = (contenido, nombre, tipo) => {
  const fd = new FormData();
  fd.append("archivo", new Blob([contenido], { type: tipo }), nombre);
  return fetch(`${api}/upload_pdf/`, { method: "POST", body: fd });
};

test("guarda un PDF válido en pendientes y aparece en el listado", async () => {
  const r = await subir("%PDF-1.4\ncontenido", "decreto 123.pdf", "application/pdf");
  assert.equal(r.status, 201);
  const d = await r.json();
  assert.match(d.archivo, /^\d+_decreto_123\.pdf$/);
  assert.ok(fs.existsSync(path.join(dirPendientes, d.archivo)));

  const lista = await (await fetch(`${api}/api/pendientes`)).json();
  assert.ok(lista.archivos.some((a) => a.archivo === d.archivo));
});

test("rechaza un archivo que dice ser PDF pero no lo es, y lo borra", async () => {
  const antes = fs.readdirSync(dirPendientes).length;
  const r = await subir("MZ esto es un ejecutable", "falso.pdf", "application/pdf");
  assert.equal(r.status, 415);
  assert.equal(fs.readdirSync(dirPendientes).length, antes);
});

test("rechaza archivos que no son PDF", async () => {
  const r = await subir("hola", "notas.txt", "text/plain");
  assert.equal(r.status, 415);
});

test("pide el campo 'archivo'", async () => {
  const r = await fetch(`${api}/upload_pdf/`, { method: "POST", body: new FormData() });
  assert.equal(r.status, 400);
});

test("el nombre del archivo no permite salir de la carpeta", async () => {
  const r = await subir("%PDF-1.4", "../../malo.pdf", "application/pdf");
  assert.equal(r.status, 201);
  const { archivo } = await r.json();
  assert.ok(!archivo.includes("/") && !archivo.includes(".."));
  assert.ok(fs.existsSync(path.join(dirPendientes, archivo)));
});

// ---------- otros ----------
test("health informa el estado del motor", async () => {
  const d = await (await fetch(`${api}/api/health`)).json();
  assert.equal(d.backend, "ok");
  assert.equal(d.motor.estado, "ok");
});

test("rutas desconocidas dan 404 en JSON", async () => {
  const r = await fetch(`${api}/no-existe`);
  assert.equal(r.status, 404);
  assert.ok((await r.json()).error);
});

test("límite de peticiones devuelve 429", async () => {
  const app = crearApp({ motorUrl: "http://127.0.0.1:1", dirPendientes, limiteChatPorMinuto: 2 });
  const srv = http.createServer(app);
  const url = await escuchar(srv);
  const pedir = () =>
    fetch(`${url}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta: "" }),
    });
  await pedir();
  await pedir();
  const r = await pedir();
  srv.close();
  assert.equal(r.status, 429);
});
