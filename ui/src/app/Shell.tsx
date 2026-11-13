import type { ReactNode } from "react";
import { Icon, type IconName } from "../ui/icons";
import { Button, IconButton } from "../ui/kit";
import { routeLabels, type Route } from "./routes";

const icons: Record<Route, IconName> = {
  course: "course",
  roadmap: "roadmap",
  schedule: "schedule",
  library: "library",
  admin: "admin",
};

type Props = {
  route: Route;
  /** The screens this learner can open; the admin screen only joins for admins. */
  routes: Route[];
  courseName: string;
  /** The preview runs without a server: say so, and hide what needs one. */
  mock: boolean;
  unread: number;
  wide?: boolean;
  onCompanion: () => void;
  onNotifications: () => void;
  onSettings: () => void;
  children: ReactNode;
};

/** The frame of every screen: a rail on wide screens, a top bar and a thumb-reach tab bar on phones. */
export function Shell({
  route,
  routes,
  courseName,
  mock,
  unread,
  wide,
  onCompanion,
  onNotifications,
  onSettings,
  children,
}: Props) {
  const links = routes.map((id) => (
    <a key={id} href={`#${id}`} aria-current={id === route ? "page" : undefined}>
      <Icon name={icons[id]} />
      <span>{routeLabels[id]}</span>
    </a>
  ));
  const bell = unread > 0 ? `Thông báo, ${unread} chưa đọc` : "Thông báo";
  return (
    <div className="app">
      <a
        className="skip"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Bỏ qua điều hướng
      </a>

      <aside className="rail">
        <a className="brand" href="#course">
          <span className="brand-mark">
            <Icon name="roadmap" size={24} />
          </span>
          Pathly
        </a>
        <div className="rail-course">
          <span className="small muted">Môn học</span>
          <strong>{courseName}</strong>
        </div>
        <nav className="nav" aria-label="Điều hướng chính">
          {links}
        </nav>
        <div className="rail-foot">
          {mock ? (
            <div className="mode">
              <strong>Bản xem thử</strong>
              Mọi thứ chỉ nằm trong trình duyệt này, không có gì được gửi đi.
            </div>
          ) : (
            <>
              <Button variant="quiet" icon="chat" onClick={onCompanion}>
                Bạn học
              </Button>
              <Button variant="quiet" icon="bell" onClick={onNotifications} aria-label={bell}>
                Thông báo{unread > 0 ? ` (${unread})` : ""}
              </Button>
            </>
          )}
          <Button variant="quiet" icon="settings" onClick={onSettings}>
            Cài đặt
          </Button>
        </div>
      </aside>

      <header className="topbar">
        <a className="brand" href="#course">
          <span className="brand-mark">
            <Icon name="roadmap" size={22} />
          </span>
          Pathly
        </a>
        <div className="row" style={{ gap: 0 }}>
          {mock ? (
            <span className="chip chip-signal">Bản xem thử</span>
          ) : (
            <>
              <IconButton icon="chat" label="Bạn học" onClick={onCompanion} />
              <IconButton icon="bell" label={bell} onClick={onNotifications}>
                {unread > 0 && <span className="badge-dot">{unread}</span>}
              </IconButton>
            </>
          )}
          <IconButton icon="settings" label="Cài đặt" onClick={onSettings} />
        </div>
      </header>

      <main id="main" className={`main ${wide ? "main-wide" : ""}`} tabIndex={-1}>
        {children}
      </main>

      <nav className="tabbar" aria-label="Điều hướng chính (di động)">
        {links}
      </nav>
    </div>
  );
}
