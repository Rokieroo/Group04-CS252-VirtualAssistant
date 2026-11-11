/** Per-device light/dark choice; base.css keys off ``data-theme`` on the root element. */
export const themes = [
  { id: "system", label: "Theo thiết bị" },
  { id: "light", label: "Sáng" },
  { id: "dark", label: "Tối" },
] as const;
export type Theme = (typeof themes)[number]["id"];

const KEY = "pathly.theme";

/** Stored text is untrusted and storage itself can throw (private mode): fall back to "system". */
export function loadTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return themes.some((t) => t.id === value) ? (value as Theme) : "system";
  } catch {
    return "system";
  }
}

export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* the choice lasts for this visit */
  }
}

/** "system" removes the override so prefers-color-scheme applies. */
export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement) {
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}
