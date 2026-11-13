import "./pages/course-setup/study-companion.css";
import { useEffect, useRef, useState } from "react";
import { authenticate } from "./api/account";
import { session } from "./api/backend";
import { courseServiceFor } from "./api/courses";
import { CourseLibrary, type OwnedCourse } from "./pages/CourseLibrary";
import { AuthScreen } from "./components/AuthScreen";
import { Modal } from "./components/Modal";
import { Shell } from "./components/Shell";
import { AppearancePicker } from "./features/appearance/AppearancePicker";
import { pageLabels, useHashPage, type Page } from "./navigation";
import { CatalogHealthPanel } from "./pages/CatalogHealthPanel";
import { CostsPage } from "./pages/CostsPage";
import { AdminCatalogPage } from "./pages/AdminCatalogPage";
import { TodayPage } from "./pages/TodayPage";
import { CoreJourney } from "./pages/CoreJourney";
import { CoursesPage } from "./pages/CoursesPage";
import { SourcesPage } from "./pages/SourcesPage";
import Workspace from "./Workspace";

const schedule: [string, string] = [
  pageLabels.Schedule,
  "Tasks, free time and study sessions planned around your week.",
];
// Pages the backend serves; Home, Mastery, Ask and Companion open Courses until they exist.
const headings: Partial<Record<Page, [string, string]>> = {
  Home: [
    pageLabels.Home,
    "Chặng đến hạn, bài ôn và mốc kiểm tra sắp tới trong ngày.",
  ],
  Library: ["", ""],
  Roadmap: ["", ""],
  Schedule: schedule,
  Sources: [
    pageLabels.Sources,
    "Learning sources you saved for your roadmap steps.",
  ],
  Workspace: schedule,
  // Admins only, opened at #costs; the backend refuses everyone else.
  Costs: [
    pageLabels.Costs,
    "What resource searches spend, per roadmap step and provider.",
  ],
  // Admin catalog review queue (Issue #104)
  Catalog: [
    pageLabels.Catalog,
    "Hàng chờ duyệt nguồn catalog và nhãn chủ đề cho quản trị viên.",
  ],
};
const available = Object.keys(headings) as Page[];

/** The app on the real backend (VITE_BACKEND_MODE=api). It never imports src/demo. */
export default function CoreApp({ mock = false }: { mock?: boolean }) {
  const [token, setToken] = useState(() => session.get() || null);
  const [page, go] = useHashPage("Library", available);
  const [settings, setSettings] = useState(false);
  const [selectedCourse, setSelectedCourse] = useState<OwnedCourse | null>(
    () => {
      const id = new URLSearchParams(location.search).get("course");
      return id ? { id, title: "Môn học đang chọn", level: "" } : null;
    },
  );
  const [showCourses, setShowCourses] = useState(
    !new URLSearchParams(location.search).has("course") &&
      !new URLSearchParams(location.search).has("kg_roadmap"),
  );
  const selectedId = useRef(selectedCourse?.id || null);
  const [journeyVersion, setJourneyVersion] = useState(0);
  const [resumeSyllabus, setResumeSyllabus] = useState(true);
  const openCourse = (
    course: OwnedCourse,
    roadmapId?: string,
    resume = false,
  ) => {
    const url = new URL(location.href);
    for (const key of [...url.searchParams.keys()])
      if (key.startsWith("kg_")) url.searchParams.delete(key);
    url.searchParams.set("course", course.id);
    if (roadmapId) url.searchParams.set("kg_roadmap", roadmapId);
    history.replaceState(null, "", url);
    selectedId.current = course.id;
    setSelectedCourse(course);
    setShowCourses(false);
    setResumeSyllabus(resume);
    setJourneyVersion((v) => v + 1);
    go(roadmapId ? "Roadmap" : "Library");
  };

  useEffect(() => {
    if (mock) return;
    const restoreCourse = () => {
      const query = new URLSearchParams(location.search);
      const id = query.get("course");
      if (id === selectedId.current) return;
      selectedId.current = id;
      setSelectedCourse(
        id ? { id, title: "Môn học đang chọn", level: "" } : null,
      );
      setShowCourses(!id && !query.has("kg_roadmap"));
      setResumeSyllabus(true);
      setJourneyVersion((v) => v + 1);
    };
    window.addEventListener("popstate", restoreCourse);
    return () => window.removeEventListener("popstate", restoreCourse);
  }, [mock]);

  if (!token && !mock)
    return <AuthScreen onAuth={setToken} authenticate={authenticate} />;

  const [title, subtitle] = headings[page]!;
  return (
    <Shell
      page={page}
      home="Library"
      go={go}
      title={title}
      subtitle={subtitle}
      course={`StudyCompanion / ${pageLabels[page]}`}
      status={mock ? "UI preview" : "Live data"}
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
                const url = new URL(location.href);
                url.search = "";
                history.replaceState(null, "", url);
                selectedId.current = null;
                setSelectedCourse(null);
                setShowCourses(true);
                setJourneyVersion((v) => v + 1);
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
      {!mock && page === "Library" && (
        <>
          {selectedCourse && (
            <div className="core-actions">
              <strong>{selectedCourse.title}</strong>
              <button
                aria-expanded={showCourses}
                onClick={() => setShowCourses(!showCourses)}
              >
                {showCourses ? "Ẩn danh sách môn học" : "Đổi môn học"}
              </button>
            </div>
          )}
          {!selectedCourse && !showCourses && (
            <button onClick={() => setShowCourses(true)}>
              Danh sách môn học
            </button>
          )}
          {showCourses && <CourseLibrary onOpen={openCourse} />}
        </>
      )}
      {(mock ||
        page === "Roadmap" ||
        selectedCourse ||
        new URLSearchParams(location.search).has("kg_roadmap")) && (
        <CoreJourney
          key={journeyVersion}
          page={page}
          go={go}
          mock={mock}
          courseId={selectedCourse?.id}
          courseTitle={selectedCourse?.title}
          onOpenCourse={openCourse}
          resumeSyllabus={resumeSyllabus}
        />
      )}
      {page === "Home" && <TodayPage go={go} />}
      {/* The sample preview has no backend for slides or the calendar. */}
      {!mock && (
        <>
          {/* Kept mounted so uploads and concept edits survive switching pages. */}
          {selectedCourse && (
            <div hidden={page !== "Library"} key={selectedCourse.id}>
              <CoursesPage
                course={selectedCourse.title}
                service={courseServiceFor(selectedCourse.id)}
              />
            </div>
          )}
          {(page === "Schedule" || page === "Workspace") && <Workspace />}
        </>
      )}
      {page === "Sources" && <SourcesPage go={go} />}
      {page === "Costs" && (
        <>
          <CostsPage />
          <CatalogHealthPanel />
        </>
      )}
      {page === "Catalog" && <AdminCatalogPage />}
    </Shell>
  );
}
