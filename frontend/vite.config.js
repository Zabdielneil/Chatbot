import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// envDir: ".." → usa el mismo .env de la raíz del repo.
// Vite solo expone al navegador las variables que empiezan por VITE_, así que LLM_API_KEY nunca llega al cliente.
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: { port: 5173 },
});
