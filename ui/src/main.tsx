import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import "@fontsource/be-vietnam-pro/700.css";
import App from "./App";
import { applyTheme, loadTheme } from "./app/theme";
import "./styles/base.css";
import "./styles/screens.css";

// Before the first render, so a saved theme never flashes the other one.
applyTheme(loadTheme());
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
