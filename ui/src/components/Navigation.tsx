import type { ReactNode } from "react";
import { nav, pageLabels, routeOf, type Page } from "../navigation";

type Items = {
  page: Page;
  go: (page: Page) => void;
  onSettings: () => void;
};

/** The main navigation entries, shared by the sidebar and the phone's bottom bar. */
export function NavItems({ page, go, onSettings }: Items) {
  return (
    <>
      {nav.map(({ page: p, icon }) => (
        <button
          key={p}
          aria-current={page === p ? "page" : undefined}
          className={page === p ? "active" : ""}
          onClick={() => go(p)}
        >
          <span aria-hidden="true">{icon}</span>
          {pageLabels[p]}
        </button>
      ))}
      <button onClick={onSettings}>
        <span aria-hidden="true">⚙</span>
        Settings
      </button>
    </>
  );
}

/** Desktop sidebar; on phones, the drawer behind the topbar's menu button. */
export function Navigation({
  home,
  open,
  onPick,
  children,
  ...items
}: Items & {
  home: Page;
  open: boolean;
  /** Called after any button or link in the sidebar, extra sections included. */
  onPick: () => void;
  children?: ReactNode;
}) {
  return (
    // Delegated so sections passed in as children close the phone drawer too.
    <aside
      id="workspace-navigation"
      className={`sidebar ${open ? "open" : ""}`}
      onClick={(e) => {
        if ((e.target as Element).closest("button, a")) onPick();
      }}
    >
      <a
        href={`#${routeOf(home)}`}
        className="brand"
        onClick={() => items.go(home)}
      >
        <span>✦</span> pathly
      </a>
      <div className="workspace-label">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">
        <NavItems {...items} />
      </nav>
      {children}
      <div className="sidebar-bottom">
        <button className="account" onClick={items.onSettings}>
          <span className="avatar" />
          Student account
        </button>
      </div>
    </aside>
  );
}
