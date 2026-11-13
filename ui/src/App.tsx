import { useCallback, useEffect, useState } from "react";
import type { Notification, User } from "./api";
import { backendEnabled, call, session } from "./api/backend";
import { routes, useRoute } from "./app/routes";
import { Shell } from "./app/Shell";
import { forgetCourse, useCourse } from "./app/useCourse";
import { AdminScreen } from "./screens/AdminScreen";
import { AuthScreen } from "./screens/AuthScreen";
import { CompanionPanel } from "./screens/CompanionPanel";
import { courseName, CourseScreen } from "./screens/CourseScreen";
import { LibraryScreen } from "./screens/LibraryScreen";
import { RoadmapScreen } from "./screens/RoadmapScreen";
import { ScheduleScreen } from "./screens/ScheduleScreen";
import { SettingsDialog } from "./screens/SettingsDialog";
import { Button, Dialog } from "./ui/kit";

const POLL_MS = 30_000;

/** Everything behind sign-in: one course, its screens, and the side panels over them. */
function Workspace({ mock, onSignOut }: { mock: boolean; onSignOut: () => void }) {
  const [route, go] = useRoute();
  const course = useCourse(mock);
  const [user, setUser] = useState<User | null>(null);
  const [notes, setNotes] = useState<Notification[]>([]);
  const [overlay, setOverlay] = useState<"companion" | "notifications" | "settings" | null>(null);

  // Session reminders arrive while the app is open; a rejected session sends the learner to sign in.
  useEffect(() => {
    if (mock) return;
    let current = true;
    const failed = () => {
      if (current && !session.get()) onSignOut();
    };
    const poll = () => call<Notification[]>("/notifications").then((list) => current && setNotes(list), failed);
    call<User>("/me").then((me) => current && setUser(me), failed);
    void poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [mock, onSignOut]);

  const allowed = routes.filter((id) => id !== "admin" || user?.role === "admin");
  const shown = allowed.includes(route) ? route : "course";
  const unread = notes.filter((n) => !n.read);
  const close = () => setOverlay(null);
  const read = async (id: string) => {
    await call(`/notifications/${id}/read`, { method: "POST" }).catch(() => {});
    setNotes((list) => list.map((n) => (n.id === id ? { ...n, read: true } : n)));
  };

  return (
    <Shell
      route={shown}
      routes={allowed}
      courseName={course.draft || course.roadmap ? courseName(course) : "Chưa có môn học"}
      mock={mock}
      unread={unread.length}
      wide={shown === "roadmap" || (shown === "course" && course.stage === "plan")}
      onCompanion={() => setOverlay("companion")}
      onNotifications={() => setOverlay("notifications")}
      onSettings={() => setOverlay("settings")}
    >
      {shown === "course" && <CourseScreen course={course} go={go} />}
      {shown === "roadmap" && <RoadmapScreen course={course} />}
      {shown === "schedule" && <ScheduleScreen course={course} />}
      {shown === "library" && <LibraryScreen mock={mock} />}
      {shown === "admin" && <AdminScreen />}

      {overlay === "companion" && <CompanionPanel onClose={close} />}
      {overlay === "settings" && (
        <SettingsDialog
          user={user}
          onUser={setUser}
          onClose={close}
          onSignOut={() => {
            void call("/auth/logout", { method: "POST" }).catch(() => {});
            onSignOut();
          }}
        />
      )}
      {overlay === "notifications" && (
        <Dialog title="Thông báo" onClose={close}>
          {unread.length === 0 && (
            <p className="muted">
              Không có thông báo mới. Lời nhắc buổi học hiện ở đây 15 phút trước giờ bắt đầu, khi ứng dụng
              đang mở.
            </p>
          )}
          <ul className="plain-list">
            {unread.map((n) => (
              <li key={n.id}>
                <span className="grow">{n.message}</span>
                <Button size="sm" onClick={() => void read(n.id)}>
                  Đã đọc
                </Button>
              </li>
            ))}
          </ul>
        </Dialog>
      )}
    </Shell>
  );
}

/** The preview (no server) opens straight away; the real app asks for an account first. */
export default function App() {
  const mock = !backendEnabled;
  const [token, setToken] = useState(() => session.get());
  const signOut = useCallback(() => {
    session.clear();
    forgetCourse();
    setToken("");
  }, []);
  if (!mock && !token) return <AuthScreen onAuth={setToken} />;
  return <Workspace key={token} mock={mock} onSignOut={signOut} />;
}
