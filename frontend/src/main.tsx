import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./ui/tokens.css";
import "./ui/base.css";
// Before anything makes a map.
import "./map/maplibreWorker.js";
import { App } from "./App.js";

const root = document.getElementById("root");
if (!root) throw new Error('index.html has no element with id "root"');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
