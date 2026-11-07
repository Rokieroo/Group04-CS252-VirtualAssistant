import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import App from "./App";
import {
  applyAppearance,
  localAppearanceStore,
} from "./features/appearance/appearance";
import "./styles.css";
import "./features/appearance/appearance.css";
// Before the first render, so a saved accent/theme never flashes the default.
applyAppearance(localAppearanceStore.load());
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
