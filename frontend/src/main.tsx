import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./ui/tokens.css";
import "./ui/base.css";
// Before anything makes a map.
import "./map/maplibreWorker.js";
import { App } from "./App.js";
import { captureEmailLinkToken } from "./features/account/emailLink.js";

// Before anything else can read or copy the address: an emailed link's token
// leaves the address bar at once.
captureEmailLinkToken();

// Fixture mode has no backend and no real draft savers, so the end-to-end
// tests get a stand-in kind of draft to prove the machinery with.
if (import.meta.env.VITE_USE_FIXTURES === "1") void import("./features/drafts/fixtureSaver.js");

const root = document.getElementById("root");
if (!root) throw new Error('index.html has no element with id "root"');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
