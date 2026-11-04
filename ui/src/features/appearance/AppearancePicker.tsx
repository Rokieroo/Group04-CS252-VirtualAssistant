import { useState } from "react";
import {
  ACCENTS,
  GRADIENTS,
  applyAppearance,
  CARD_STYLES,
  localAppearanceStore,
  THEMES,
  type Appearance,
  type AppearanceStore,
} from "./appearance";

type Props = { store?: AppearanceStore };

/** Appearance choices apply at once and are remembered on this device. */
export function AppearancePicker({ store = localAppearanceStore }: Props) {
  const [value, setValue] = useState<Appearance>(() => store.load());
  const choose = (next: Appearance) => {
    setValue(next);
    applyAppearance(next);
    store.save(next);
  };

  return (
    <section className="appearance" aria-labelledby="appearance-title">
      <h3 id="appearance-title">Appearance</h3>
      <fieldset>
        <legend>Accent color</legend>
        <p className="appearance-group-label">Classic colors</p>
        <div className="swatches">
          {ACCENTS.map((a) => (
            <label key={a.id} className="swatch" data-accent={a.id}>
              <input
                type="radio"
                name="accent"
                value={a.id}
                checked={value.accent === a.id}
                onChange={() => choose({ ...value, accent: a.id })}
              />
              <span className="swatch-dot" aria-hidden="true" />
              {a.label}
            </label>
          ))}
        </div>
        <p className="appearance-group-label">Multi-color gradients</p>
        <div className="gradient-swatches">
          {GRADIENTS.map((gradient) => (
            <label key={gradient.id} className="swatch gradient-choice">
              <input
                type="radio"
                name="accent"
                value={gradient.id}
                checked={value.accent === gradient.id}
                onChange={() => choose({ ...value, accent: gradient.id })}
              />
              <span
                className="gradient-preview"
                style={{ background: `linear-gradient(90deg, ${gradient.colors.join(", ")})` }}
                aria-hidden="true"
              />
              <span>{gradient.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Theme</legend>
        <div className="segmented">
          {THEMES.map((t) => (
            <label key={t.id}>
              <input
                type="radio"
                name="theme"
                value={t.id}
                checked={value.theme === t.id}
                onChange={() => choose({ ...value, theme: t.id })}
              />
              {t.label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Card style</legend>
        <div className="card-style-choices">
          {CARD_STYLES.map((style) => (
            <label key={style.id} className="card-style-choice">
              <input
                type="radio"
                name="card-style"
                value={style.id}
                checked={value.cardStyle === style.id}
                onChange={() => choose({ ...value, cardStyle: style.id })}
              />
              <span className={`card-style-preview ${style.id}`} aria-hidden="true" />
              <span>{style.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <p>Changes apply right away and are saved on this device.</p>
    </section>
  );
}
