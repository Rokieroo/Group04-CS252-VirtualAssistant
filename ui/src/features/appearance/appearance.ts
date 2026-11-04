// Per-device look (accent + light/dark). Kept apart from the demo state so resetting the demo keeps it.
// Preset colours live in styles.css ([data-accent="…"]); this module only names them.
export const ACCENTS = [
  { id: "violet", label: "Violet" },
  { id: "ocean", label: "Ocean" },
  { id: "forest", label: "Forest" },
  { id: "sunset", label: "Sunset" },
  { id: "slate", label: "Slate" },
] as const;
export const GRADIENTS = [
  {
    id: "visible-spectrum",
    label: "Visible Spectrum",
    colors: [
      "#aa00ff",
      "#8400ff",
      "#6a00ff",
      "#004cff",
      "#00cfff",
      "#00ff76",
      "#fff200",
      "#ff9800",
      "#ff2000",
      "#ff0000",
      "#ff0000",
    ],
  },
  {
    id: "holographic-candy",
    label: "Holographic Candy",
    colors: ["#ff3ed1", "#a855f7", "#4cc9f0", "#5ef2c2", "#fff275"],
  },
  {
    id: "neon-aura",
    label: "Neon Aura",
    colors: ["#6500ff", "#006cff", "#00e5ff", "#00f5a0", "#d9ff00"],
  },
  {
    id: "bioluminescent-ocean",
    label: "Bioluminescent Ocean",
    colors: ["#020617", "#003b73", "#0077b6", "#00d9c0", "#7cff6b"],
  },
  {
    id: "cosmic-plasma",
    label: "Cosmic Plasma",
    colors: ["#120020", "#5a00ff", "#e000ff", "#ff166f", "#ff7a00"],
  },
  {
    id: "dragon-fire",
    label: "Dragon Fire",
    colors: ["#160000", "#700000", "#ff1800", "#ff7800", "#ffe600"],
  },
  {
    id: "fantasy-spectrum",
    label: "Fantasy Spectrum",
    colors: [
      "#240046",
      "#7209b7",
      "#4361ee",
      "#00cfff",
      "#00e676",
      "#fff000",
      "#ff7900",
      "#ff1900",
      "#5a0000",
    ],
  },
  {
    id: "quantum-neon",
    label: "Quantum Neon",
    colors: ["#050014", "#7b2cff", "#3a00ff", "#00a6ff", "#00f5ff", "#00ffb7"],
  },
  {
    id: "mystic-amethyst",
    label: "Mystic Amethyst",
    colors: ["#10002b", "#3c096c", "#7b2cbf", "#c040ff", "#ff66c4"],
  },
  {
    id: "ai-core",
    label: "AI Core",
    colors: ["#020617", "#003cff", "#0077ff", "#00d9ff", "#00ffd1", "#a6ff00"],
  },
  {
    id: "cyberpunk",
    label: "Cyberpunk",
    colors: ["#09001f", "#6100ff", "#ff00c8", "#ff275d", "#00e5ff"],
  },
  {
    id: "celestial-chroma",
    label: "Celestial Chroma",
    colors: ["#090014", "#5016a8", "#d6a72b", "#fff3a6"],
  },
  {
    id: "celestial-prism",
    label: "Celestial Prism",
    colors: [
      "#02000d",
      "#10003d",
      "#3b008f",
      "#7928ca",
      "#2563ff",
      "#00cfff",
      "#7df9ff",
      "#fff7d6",
      "#ffd166",
      "#ff5ec4",
      "#4a003f",
    ],
  },
] as const;

export const THEMES = [
  { id: "system", label: "Match device" },
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
] as const;

export type Accent =
  (typeof ACCENTS)[number]["id"] | (typeof GRADIENTS)[number]["id"];
export type Theme = (typeof THEMES)[number]["id"];
export const CARD_STYLES = [
  { id: "standard", label: "Standard" },
  { id: "cloudy", label: "Cloudy" },
] as const;
export type CardStyle = (typeof CARD_STYLES)[number]["id"];
export type Appearance = { accent: Accent; theme: Theme; cardStyle: CardStyle };

export const DEFAULT_APPEARANCE: Appearance = {
  accent: "violet",
  theme: "system",
  cardStyle: "standard",
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
    cardStyle: CARD_STYLES.some((style) => style.id === x.cardStyle)
      ? (x.cardStyle as CardStyle)
      : DEFAULT_APPEARANCE.cardStyle,
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

function linearGradient(colors: readonly string[], angle = 90): string {
  return `linear-gradient(${angle}deg, ${colors.join(", ")})`;
}

/** styles.css keys off appearance data attributes; default choices remove their overrides. */
export function applyAppearance(
  appearance: Appearance,
  root: HTMLElement = document.documentElement,
) {
  root.dataset.accent = appearance.accent;
  const gradient = GRADIENTS.find((item) => item.id === appearance.accent);
  if (gradient) {
    const fullGradient = linearGradient(gradient.colors);
    root.dataset.gradient = "true";
    root.style.setProperty("--gradient-display", fullGradient);
    root.style.setProperty(
      "--gradient-display-vertical",
      linearGradient(gradient.colors, 180),
    );
    root.style.setProperty("--gradient-brand", fullGradient);
    root.style.setProperty(
      "--gradient-text-light",
      linearGradient(
        gradient.colors.map(
          (color) => `color-mix(in oklab, ${color} 35%, #101828)`,
        ),
      ),
    );
    root.style.setProperty(
      "--gradient-text-dark",
      linearGradient(
        gradient.colors.map(
          (color) => `color-mix(in oklab, ${color} 45%, white)`,
        ),
      ),
    );
    // A dark veil preserves every hue while keeping white text legible on filled controls.
    root.style.setProperty("--gradient-veil", "#0009");
    root.style.setProperty(
      "--accent-a",
      `color-mix(in oklab, ${gradient.colors[0]} 40%, #101828)`,
    );
    root.style.setProperty(
      "--accent-b",
      `color-mix(in oklab, ${gradient.colors[gradient.colors.length - 1]} 40%, #101828)`,
    );
  } else {
    delete root.dataset.gradient;
    for (const token of [
      "--gradient-display",
      "--gradient-display-vertical",
      "--gradient-brand",
      "--gradient-text-light",
      "--gradient-text-dark",
      "--gradient-veil",
      "--accent-a",
      "--accent-b",
    ])
      root.style.removeProperty(token);
  }
  if (appearance.theme === "system") delete root.dataset.theme;
  else root.dataset.theme = appearance.theme;
  if (appearance.cardStyle === "standard") delete root.dataset.cardStyle;
  else root.dataset.cardStyle = appearance.cardStyle;
}
