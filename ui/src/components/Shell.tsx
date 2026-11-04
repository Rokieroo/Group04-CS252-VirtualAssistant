import { useState, type ReactNode } from "react";
import type { Page } from "../navigation";
import { today } from "../time";
import { Navigation, NavItems } from "./Navigation";

type Props = {
  page: Page;
  /** Where the logo leads: Home in the demo, Courses on the real backend. */
  home: Page;
  go: (page: Page) => void;
  title: string;
  subtitle: string;
  course: string;
  /** The mode badge in the topbar, e.g. "Demo mode". */
  status: string;
  onSettings: () => void;
  /** Extra topbar buttons, before the account button. */
  actions?: ReactNode;
  /** Extra sidebar sections, below the main navigation. */
  sidebar?: ReactNode;
  /** Dialogs and toasts, rendered after the page. */
  overlays?: ReactNode;
  children: ReactNode;
};

/** The layout both apps share: sidebar, topbar, page heading and phone bottom bar. */
export function Shell({
  page,
  home,
  go,
  title,
  subtitle,
  course,
  status,
  onSettings,
  actions,
  sidebar,
  overlays,
  children,
}: Props) {
  const [menu, setMenu] = useState(false);
  const navigate = (next: Page) => {
    setMenu(false);
    go(next);
  };
  const settings = () => {
    setMenu(false);
    onSettings();
  };
  return (
    <div className={`app ${home === "Library" ? "study-companion" : ""}`}>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <Navigation
        page={page}
        home={home}
        open={menu}
        onPick={() => setMenu(false)}
        go={navigate}
        onSettings={settings}
      >
        {sidebar}
      </Navigation>
      <main id="main">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="Toggle navigation"
            aria-controls="workspace-navigation"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            ☰
          </button>
          <strong className="course-name">{course}</strong>
          <span>
            {today().toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </span>
          <div>
            <span className="demo-label">{status}</span>
            {actions}
            <button
              className="icon-button"
              aria-label="Account settings"
              onClick={settings}
            >
              <span className="avatar" aria-hidden="true" />
            </button>
          </div>
        </header>
        {title && (
          <div className="page-heading" key={page}>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
        )}
        {children}
      </main>
      <nav className="bottom-nav" aria-label="Main navigation (mobile)">
        <NavItems page={page} go={navigate} onSettings={settings} />
      </nav>
      {overlays}
    </div>
  );
}
