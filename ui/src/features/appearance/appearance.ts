// Per-device look (accent + light/dark). Kept apart from the demo state so resetting the demo keeps it.
// Preset colours live in styles.css ([data-accent="…"]); this module only names them.
import { GRADIENTS } from "./gradients";
export const ACCENTS = [
  { id: "violet", label: "Violet" },
  { id: "ocean", label: "Ocean" },
  { id: "forest", label: "Forest" },
  { id: "sunset", label: "Sunset" },
  { id: "slate", label: "Slate" },
] as const;
export const THEMES = [
  { id: "system", label: "Match device" },
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
] as const;

export type Accent = (typeof ACCENTS)[number]["id"] | (typeof GRADIENTS)[number]["id"];
export type Theme = (typeof THEMES)[number]["id"];
export type Appearance = { accent: Accent; theme: Theme };

export const DEFAULT_APPEARANCE: Appearance = {
  accent: "violet",
  theme: "system",
};
const KEY = "pathly.appearance.v1";

/** Stored text is untrusted: unknown or malformed values fall back to the defaults. */
export function parseAppearance(raw: string | null): Appearance {
  let x: Partial<Record<keyof Appearance, unknown>> = {};
  try {
    const parsed: unknown = JSON.parse(raw ?? "null");
    if (parsed && typeof parsed === "object") x = parsed;
  } catch {
    // keep defaults
  }
  return {
    accent: [...ACCENTS, ...GRADIENTS].some((a) => a.id === x.accent)
      ? (x.accent as Accent)
      : DEFAULT_APPEARANCE.accent,
    theme: THEMES.some((t) => t.id === x.theme)
      ? (x.theme as Theme)
      : DEFAULT_APPEARANCE.theme,
  };
}

export interface AppearanceStore {
  load(): Appearance;
  save(appearance: Appearance): void;
}

type KeyValueStorage = Pick<Storage, "getItem" | "setItem">;

/** Storage is resolved lazily: reading `localStorage` itself can throw (private mode, blocked site data). */
export function createAppearanceStore(
  getStorage: () => KeyValueStorage,
): AppearanceStore {
  return {
    load() {
      try {
        return parseAppearance(getStorage().getItem(KEY));
      } catch {
        return DEFAULT_APPEARANCE;
      }
    },
    save(appearance) {
      try {
        getStorage().setItem(KEY, JSON.stringify(appearance));
      } catch {
        // storage unavailable: the choice lasts for this visit
      }
    },
  };
}

export const localAppearanceStore = createAppearanceStore(
  () => window.localStorage,
);

/** styles.css keys off data-accent / data-theme; "system" removes the override so prefers-color-scheme applies. */
export function applyAppearance(
  appearance: Appearance,
  root: HTMLElement = document.documentElement,
) {
  root.dataset.accent = appearance.accent;
  const gradient = GRADIENTS.find((g) => g.id === appearance.accent);
  if (gradient) {
    const colors = gradient.colors as readonly string[];
    root.style.setProperty("--gradient-brand", `linear-gradient(90deg, ${colors.join(", ")})`);
    root.style.setProperty("--accent-a", `color-mix(in oklab, ${colors[0]} 40%, #101828)`);
    root.style.setProperty("--accent-b", `color-mix(in oklab, ${colors[colors.length - 1]} 40%, #101828)`);
  } else {
    for (const token of ["--gradient-brand", "--accent-a", "--accent-b"]) root.style.removeProperty(token);
  }
  if (appearance.theme === "system") delete root.dataset.theme;
  else root.dataset.theme = appearance.theme;
}
