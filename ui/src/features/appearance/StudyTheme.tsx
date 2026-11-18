import { useLayoutEffect, useSyncExternalStore, type ReactNode } from "react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";
import { APPEARANCE_EVENT, currentAppearanceTheme } from "./appearance";

const subscribe = (listener: () => void) => {
  window.addEventListener(APPEARANCE_EVENT, listener);
  return () => window.removeEventListener(APPEARANCE_EVENT, listener);
};

/** One provider for controls, native dialogs and saved Light/Dark/Windy/Flame/device mode. */
export function StudyTheme({ children }: { children: ReactNode }) {
  const mode = useSyncExternalStore(subscribe, currentAppearanceTheme);
  useLayoutEffect(() => {
    if (mode === "windy" || mode === "flame") {
      document.documentElement.dataset.theme = mode;
    }
  }, [mode]);
  return (
    <Theme
      theme={neutralTheme}
      mode={mode === "windy" || mode === "flame" ? "light" : mode}
    >
      {children}
    </Theme>
  );
}
