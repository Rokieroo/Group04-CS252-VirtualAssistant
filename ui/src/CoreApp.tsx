import { useState } from "react";
import { authenticate } from "./api/account";
import { session } from "./api/backend";
import { backendCourses, currentCourse } from "./api/courses";
import { AuthScreen } from "./components/AuthScreen";
import { Modal } from "./components/Modal";
import { Shell } from "./components/Shell";
import { AppearancePicker } from "./features/appearance/AppearancePicker";
import { pageLabels, useHashPage, type Page } from "./navigation";
import { CostsPage } from "./pages/CostsPage";
import { CoursesPage } from "./pages/CoursesPage";
import { RoadmapPage } from "./pages/RoadmapPage";
import { SourcesPage } from "./pages/SourcesPage";
import Workspace from "./Workspace";

const schedule: [string, string] = [
  pageLabels.Schedule,
  "Tasks, free time and study sessions planned around your week.",
];
// Pages the backend serves; Home, Mastery, Ask and Companion open Courses until they exist.
const headings: Partial<Record<Page, [string, string]>> = {
  Library: [
    `${pageLabels.Library} · ${currentCourse.name}`,
    "Upload your slides, then confirm the concepts the AI proposes.",
  ],
  Roadmap: [pageLabels.Roadmap, "Weekly steps from your syllabus, with exam milestones."],
  Schedule: schedule,
  Sources: [pageLabels.Sources, "Learning sources you saved for your roadmap steps."],
  Workspace: schedule,
  // Admins only, opened at #costs; the backend refuses everyone else.
  Costs: [pageLabels.Costs, "What resource searches spend, per roadmap step and provider."],
};
const available = Object.keys(headings) as Page[];

/** The app on the real backend (VITE_BACKEND_MODE=api). It never imports src/demo. */
export default function CoreApp() {
  const [token, setToken] = useState(() => session.get() || null);
  const [page, go] = useHashPage("Library", available);
  const [settings, setSettings] = useState(false);
  if (!token) return <AuthScreen onAuth={setToken} authenticate={authenticate} />;

  const [title, subtitle] = headings[page]!;
  return (
    <Shell
      page={page}
      home="Library"
      go={go}
      title={title}
      subtitle={subtitle}
      course={currentCourse.name}
      status="Live data"
      onSettings={() => setSettings(true)}
      overlays={
        settings && (
          <Modal title="Settings" onClose={() => setSettings(false)}>
            <AppearancePicker />
            <hr />
            <button
              className="button"
              type="button"
              onClick={() => {
                session.clear();
                setSettings(false);
                setToken(null);
              }}
            >
              Sign out
            </button>
          </Modal>
        )
      }
    >
      {/* Kept mounted so uploads and concept edits survive switching pages. */}
      <div hidden={page !== "Library"}>
        <CoursesPage course={currentCourse.name} service={backendCourses} />
      </div>
      {page === "Roadmap" && <RoadmapPage go={go} />}
      {(page === "Schedule" || page === "Workspace") && <Workspace />}
      {page === "Sources" && <SourcesPage go={go} />}
      {page === "Costs" && <CostsPage />}
    </Shell>
  );
}
