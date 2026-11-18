import "./personal-learning.css";
import { useEffect, useState } from "react";
import { SourcePageDialog } from "./course-setup/SourcePageDialog";
import { Button } from "../components/Button";
import { pageLabels, type Page } from "../navigation";
import { call } from "../api/backend";
import { editLibrary, type LibraryItem } from "../api/personalLibrary";

function SavedItem({
  item,
  onChange,
}: {
  item: LibraryItem;
  onChange: (item: LibraryItem) => void;
}) {
  const [reading, setReading] = useState(false);
  const [note, setNote] = useState(item.note);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(change: Parameters<typeof editLibrary>[2]) {
    setBusy(true);
    setError("");
    try {
      await editLibrary(item.node_id, item.source_key, change);
      onChange({ ...item, ...change });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const query = new URLSearchParams({
    course: item.course_id,
    kg_roadmap: item.roadmap_id,
    kg_node: item.node_id,
  });
  return (
    <article className="card core-panel">
      <h3>{item.title}</h3>
      {item.url && /^https?:\/\//i.test(item.url) && (
        <a href={item.url} target="_blank" rel="noreferrer">
          Đọc nguồn
        </a>
      )}
      {item.page != null && (
        <button onClick={() => setReading(true)}>Đọc trang {item.page}</button>
      )}
      {reading && item.page != null && (
        <SourcePageDialog
          courseId={item.course_id}
          sourceId={item.source_key}
          page={item.page}
          onClose={() => setReading(false)}
        />
      )}
      <p>
        {item.course_title} ·{" "}
        <a href={`?${query}#roadmap`}>{item.node_title}</a>
      </p>
      <fieldset disabled={busy}>
        <legend>
          {item.state === "hidden"
            ? "Đã ẩn"
            : item.state === "pinned"
              ? "Đã ghim"
              : "Ghi chú"}
        </legend>
        <label>
          Ghi chú cho nguồn ở chặng này
          <textarea
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="core-actions">
          <button
            disabled={note.trim() === item.note}
            onClick={() => save({ note: note.trim() })}
          >
            Lưu ghi chú
          </button>
          <button
            onClick={() =>
              save({ state: item.state === "pinned" ? "none" : "pinned" })
            }
          >
            {item.state === "pinned" ? "Bỏ ghim" : "Ghim nguồn"}
          </button>
          <button
            onClick={() =>
              save({ state: item.state === "hidden" ? "none" : "hidden" })
            }
          >
            {item.state === "hidden" ? "Hiện lại" : "Ẩn nguồn"}
          </button>
        </div>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </article>
  );
}

export function SourcesPage({
  go,
  live = false,
}: {
  go: (page: Page) => void;
  live?: boolean;
}) {
  const [items, setItems] = useState<LibraryItem[] | null>(null),
    [error, setError] = useState(""),
    [revision, refresh] = useState(0);
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState("");
  useEffect(() => {
    if (!live) return;
    let active = true;
    setError("");
    setItems(null);
    call<LibraryItem[]>("/me/library")
      .then((data) => {
        if (active) setItems(data);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [live, revision]);
  if (!live)
    return (
      <section className="card empty">
        <h3>No saved sources yet</h3>
        <Button onClick={() => go("Roadmap")}>Open {pageLabels.Roadmap}</Button>
      </section>
    );
  const visible = items?.filter(
    (i) =>
      (!filter || filter === i.state) &&
      i.course_title
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <section className="personal-library" aria-label="Thư viện cá nhân">
      <h2>Thư viện cá nhân</h2>
      {error ? (
        <p role="alert">
          {error} <button onClick={() => refresh((r) => r + 1)}>Thử lại</button>
        </p>
      ) : items === null ? (
        <p role="status">Đang tải nguồn…</p>
      ) : (
        <>
          <label>
            Tìm theo môn{" "}
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label>
            Trạng thái{" "}
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">Tất cả</option>
              <option value="pinned">Đã ghim</option>
              <option value="hidden">Đã ẩn</option>
            </select>
          </label>
          {!visible?.length && (
            <p>
              {items.length
                ? "Không có nguồn phù hợp."
                : "Chưa có nguồn. Mở một chặng trên lộ trình để ghim nguồn."}
            </p>
          )}
          {visible?.map((item) => (
            <SavedItem
              key={JSON.stringify([item.node_id, item.source_key])}
              item={item}
              onChange={(next) =>
                setItems(
                  (old) =>
                    old?.flatMap((i) =>
                      i.node_id === next.node_id &&
                      i.source_key === next.source_key
                        ? next.state === "none" && !next.note
                          ? []
                          : [next]
                        : [i],
                    ) ?? [],
                )
              }
            />
          ))}
          <Button onClick={() => go("Roadmap")}>Mở lộ trình</Button>
        </>
      )}
    </section>
  );
}
