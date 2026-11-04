import { useState } from "react";
import { GRADIENTS } from "./gradients";
import {
  ACCENTS,
  applyAppearance,
  localAppearanceStore,
  THEMES,
  type Appearance,
  type AppearanceStore,
} from "./appearance";

type Props = { store?: AppearanceStore };

/** Accent and theme choices; each change applies at once and is remembered on this device. */
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
      </fieldset>
      <fieldset>
        <legend>Gradient colors</legend>
        <div className="swatches">
          {GRADIENTS.map((g) => (
            <label key={g.id} className="swatch">
              <input type="radio" name="accent" value={g.id} checked={value.accent === g.id}
                onChange={() => choose({ ...value, accent: g.id })} />
              <span className="swatch-dot" aria-hidden="true"
                style={{ background: `linear-gradient(90deg, ${g.colors.join(", ")})` }} />
              {g.label}
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
      <p>Changes apply right away and are saved on this device.</p>
    </section>
  );
}
