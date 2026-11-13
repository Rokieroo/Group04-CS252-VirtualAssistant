import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  fetchCatalogReviewQueue,
  rejectCatalogResource,
  verifyCatalogResource,
  type CatalogReviewItem,
} from "../api/catalog";
import { loadCatalogHealth, loadCosts } from "../api/costs";
import type { CatalogHealth, CostReport } from "../api/types";
import { dateTimeLabel, explain } from "../app/text";
import { Button, Chip, Field, Loading, Notice, PageHead, Tabs } from "../ui/kit";

const tabs = [
  { id: "queue", label: "Hàng chờ duyệt" },
  { id: "health", label: "Kho nguồn" },
  { id: "costs", label: "Chi phí" },
] as const;
type Tab = (typeof tabs)[number]["id"];

const usd = (value: number) => `$${value.toFixed(value && value < 0.01 ? 4 : 2)}`;
const when = (value: string | null) => (value ? dateTimeLabel(value) : "Chưa có");

/** Loads again whenever ``watch`` changes and renders the value, a spinner, or the error. */
function Loaded<T>({
  load,
  watch,
  children,
}: {
  load: () => Promise<T>;
  watch: unknown;
  children: (value: T) => ReactNode;
}) {
  const [state, setState] = useState<{ value?: T; error?: string }>({});
  const loader = useRef(load);
  loader.current = load;
  useEffect(() => {
    let current = true;
    setState({});
    loader.current().then(
      (value) => current && setState({ value }),
      (e) => current && setState({ error: explain(e) }),
    );
    return () => {
      current = false;
    };
  }, [watch]);
  if (state.error) return <Notice tone="error">{state.error}</Notice>;
  if (state.value === undefined) return <Loading />;
  return <>{children(state.value)}</>;
}

function Table({ head, rows, empty }: { head: string[]; rows: ReactNode[][]; empty: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {head.map((label, i) => (
              <th key={label} scope="col" className={i ? "num" : ""}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) =>
                i ? (
                  <td key={i} className="num">
                    {cell}
                  </td>
                ) : (
                  <th key={i} scope="row">
                    {cell}
                  </th>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Figures({ items }: { items: [string, ReactNode, string?][] }) {
  return (
    <dl className="figures">
      {items.map(([label, value, note]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
          {note && <dd className="muted small">{note}</dd>}
        </div>
      ))}
    </dl>
  );
}

/** What resource searches cost, per roadmap step and provider (issue #69). */
function Costs() {
  const [days, setDays] = useState(7);
  return (
    <div className="stack">
      <Field label="Khoảng thời gian" className="narrow">
        <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
          {[7, 30, 90].map((value) => (
            <option key={value} value={value}>
              {value} ngày gần đây
            </option>
          ))}
        </select>
      </Field>
      <Loaded<CostReport> load={() => loadCosts(days)} watch={days}>
        {({ totals, nodes, providers, daily }) => (
          <>
            <Figures
              items={[
                ["Tổng chi phí", usd(totals.cost_usd), `LLM ${usd(totals.llm_cost_usd)}, tìm kiếm ${usd(totals.search_cost_usd)}`],
                ["Mỗi lượt tìm", usd(totals.cost_per_search_usd), `${totals.searches} lượt, ${totals.cache_hits} từ bộ nhớ đệm`],
                ["Lượt gọi LLM hôm nay", totals.llm_calls_today, `${totals.llm_calls} trong khoảng này`],
              ]}
            />
            <section className="section">
              <h2>Theo bước của lộ trình</h2>
              <Table
                head={["Bước", "Lượt tìm", "Từ bộ nhớ đệm", "Lượt gọi LLM", "Chi phí"]}
                rows={nodes.map((n) => [n.node_title, n.searches, n.cache_hits, n.llm_calls, usd(n.cost_usd)])}
                empty="Không có lượt tìm nguồn nào trong khoảng này."
              />
            </section>
            <section className="section">
              <h2>Nhà cung cấp tìm kiếm</h2>
              <Table
                head={["Nhà cung cấp", "Lượt gọi", "Hôm nay", "Lỗi", "Độ trễ TB", "Chi phí"]}
                rows={providers.map((p) => [
                  p.provider,
                  p.calls,
                  p.calls_today,
                  p.errors,
                  `${Math.round(p.avg_latency_ms)} ms`,
                  usd(p.cost_usd),
                ])}
                empty="Chưa có lượt gọi nào."
              />
            </section>
            <section className="section">
              <h2>Theo ngày</h2>
              <Table
                head={["Ngày", "Lượt tìm", "Chi phí"]}
                rows={daily.map((d) => [d.day, d.searches, usd(d.cost_usd)])}
                empty="Chưa có dữ liệu theo ngày."
              />
            </section>
          </>
        )}
      </Loaded>
    </div>
  );
}

/** Where roadmaps lack sources and how the catalog keeps up (issue #105). */
function Health() {
  return (
    <Loaded<CatalogHealth> load={() => loadCatalogHealth(7)} watch={0}>
      {(health) => (
        <div className="stack">
          <Figures
            items={[
              ["Bước thiếu nguồn", health.insufficient_nodes, "có ít hơn 2 nguồn"],
              [
                "Nguồn đã kiểm chứng",
                health.resources.verified ?? 0,
                `${health.resources.pending ?? 0} chờ duyệt, ${health.resources.rejected ?? 0} bị loại`,
              ],
              ["Liên kết hỏng", health.dead_links],
            ]}
          />
          <section className="section">
            <h2>Môn thiếu nguồn</h2>
            <Table
              head={["Môn", "Số bước"]}
              rows={health.gaps.map((g) => [g.name, g.nodes])}
              empty="Mọi bước của lộ trình đều đủ nguồn."
            />
          </section>
          <section className="section">
            <h2>Bộ nạp nguồn, {health.days} ngày gần đây</h2>
            <Table
              head={["Bộ nạp", "Lượt chạy", "Nguồn mới", "Lỗi", "Lỗi gần nhất", "Chạy lần cuối"]}
              rows={health.connectors.map((c) => [
                c.connector,
                c.runs,
                c.created,
                c.errors,
                c.last_error ?? "Không",
                when(c.last_run_at),
              ])}
              empty="Không có lượt chạy nào trong khoảng này."
            />
          </section>
          <section className="section">
            <h2>Các lượt lấp chỗ thiếu</h2>
            <Table
              head={["Thời điểm", "Loại", "Bước thiếu: trước, sau", "Lượt nạp đã xếp"]}
              rows={health.gap_runs.map((run) => [
                when(run.at),
                run.kind === "fill_gaps" ? "Lấp chỗ thiếu hằng đêm" : "Khớp lại nguồn",
                `${run.insufficient_before}, ${run.insufficient_after}`,
                run.ingest_jobs,
              ])}
              empty="Chưa có lượt nào."
            />
          </section>
          {health.dead.length > 0 && (
            <section className="section">
              <h2>Liên kết hỏng</h2>
              <ul className="plain-list">
                {health.dead.map((link) => (
                  <li key={link.id}>
                    <a className="grow" href={link.url} target="_blank" rel="noreferrer">
                      {link.title}
                    </a>
                    <span className="muted small">
                      HTTP {link.http_status ?? "không phản hồi"}, kiểm tra {when(link.last_checked_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Loaded>
  );
}

// Must match `licenses` in data/policy/catalog_sources.yaml: verify rejects any other.
const LICENSES = [
  "CC-BY-3.0",
  "CC-BY-4.0",
  "CC-BY-SA-4.0",
  "CC-BY-NC-SA-3.0",
  "CC-BY-NC-SA-4.0",
  "CC0-1.0",
  "VN-LEGAL-TEXT",
  "ALL-RIGHTS-RESERVED",
];
const VERIFY_REASONS = [
  "Footer confirms CC-BY-4.0",
  "Verified OER educational source",
  "Legitimate university publication",
  "Public domain academic notes",
];
const REJECT_REASONS = ["takedown", "paywalled / login required", "pirated or unauthorized mirror", "broken link / 404"];
const results: Record<string, "route" | "danger" | "signal" | "plain"> = {
  pass: "route",
  fail: "danger",
  warn: "signal",
  review: "signal",
};

/**
 * Sources waiting for a person (issues #101, #104). Built for speed: J/K move through the
 * queue, V verifies and R rejects the open source with the reasons chosen on the right.
 */
function Queue() {
  const [items, setItems] = useState<CatalogReviewItem[] | null>(null);
  const [index, setIndex] = useState(0);
  const [search, setSearch] = useState("");
  const [license, setLicense] = useState<Record<string, string>>({});
  const [verifyReason, setVerifyReason] = useState(VERIFY_REASONS[0]);
  const [rejectReason, setRejectReason] = useState(REJECT_REASONS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    let current = true;
    fetchCatalogReviewQueue(100).then(
      (list) => current && setItems(list),
      (e) => {
        if (!current) return;
        setError(explain(e));
        setItems([]);
      },
    );
    return () => {
      current = false;
    };
  }, []);

  const term = search.trim().toLowerCase();
  const shown = (items ?? []).filter(
    (item) => !term || `${item.title} ${item.url} ${item.provider}`.toLowerCase().includes(term),
  );
  const open = shown[Math.min(index, shown.length - 1)] ?? null;
  const chosen = open ? (license[open.id] ?? open.license ?? "") : "";

  const decide = async (verify: boolean) => {
    if (!open || busy) return;
    setBusy(true);
    setError("");
    try {
      if (verify) await verifyCatalogResource(open.id, verifyReason, chosen || null);
      else await rejectCatalogResource(open.id, rejectReason);
      setItems((list) => (list ?? []).filter((item) => item.id !== open.id));
      setDone(`${verify ? "Đã duyệt" : "Đã loại"}: ${open.title}`);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };
  // The handler reads the latest state through this ref, so the listener is bound once.
  const keys = useRef({ decide, count: shown.length });
  keys.current = { decide, count: shown.length };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if ((event.target as HTMLElement).closest("input, textarea, select, [role='dialog']")) return;
      const key = event.key.toLowerCase();
      if (key === "j") setIndex((i) => Math.min(i + 1, Math.max(0, keys.current.count - 1)));
      else if (key === "k") setIndex((i) => Math.max(0, i - 1));
      else if (key === "v") void keys.current.decide(true);
      else if (key === "r") void keys.current.decide(false);
      else return;
      event.preventDefault();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  if (items === null) return <Loading>Đang tải hàng chờ…</Loading>;
  return (
    <div className="stack">
      {error && <Notice tone="error">{error}</Notice>}
      {done && <Notice tone="success">{done}</Notice>}
      <div className="queue">
        <div className="queue-list">
          <Field label={`Tìm trong ${items.length} nguồn chờ duyệt`}>
            <input
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setIndex(0);
              }}
            />
          </Field>
          {shown.length === 0 ? (
            <p className="muted">
              {items.length ? "Không nguồn nào khớp." : "Hàng chờ trống. Không còn nguồn nào cần duyệt."}
            </p>
          ) : (
            <ul>
              {shown.map((item, i) => (
                <li key={item.id}>
                  <button type="button" aria-pressed={item === open} onClick={() => setIndex(i)}>
                    <strong>{item.title}</strong>
                    <span className="muted small">{item.provider}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Phím tắt: J và K để di chuyển, V để duyệt, R để loại.</p>
        </div>

        {open && (
          <section className="queue-open" aria-label={`Đang xem: ${open.title}`}>
            <h2>{open.title}</h2>
            <a href={open.url} target="_blank" rel="noreferrer">
              {open.url}
            </a>
            <div className="row">
              <Chip>{open.provider}</Chip>
              <Chip>{open.license ?? "Chưa rõ giấy phép"}</Chip>
            </div>
            <h3>Kết quả kiểm tra tự động</h3>
            <ul className="plain-list">
              {open.checks.map((check) => (
                <li key={check.check}>
                  <Chip tone={results[check.result] ?? "plain"}>{check.result}</Chip>
                  <span className="grow">
                    <strong>{check.check}</strong>
                    {check.reason && <span className="muted small"> {check.reason}</span>}
                  </span>
                </li>
              ))}
            </ul>
            <div className="form-grid">
              <Field label="Giấy phép khi duyệt">
                <select
                  value={chosen}
                  onChange={(event) => setLicense((all) => ({ ...all, [open.id]: event.target.value }))}
                >
                  <option value="">Giữ giấy phép đã nhận diện</option>
                  {LICENSES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Lý do duyệt">
                <select value={verifyReason} onChange={(event) => setVerifyReason(event.target.value)}>
                  {VERIFY_REASONS.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </Field>
              <Field label="Lý do loại">
                <select value={rejectReason} onChange={(event) => setRejectReason(event.target.value)}>
                  {REJECT_REASONS.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="row">
              <Button variant="primary" icon="check" disabled={busy} onClick={() => void decide(true)}>
                Duyệt (V)
              </Button>
              <Button variant="danger" icon="close" disabled={busy} onClick={() => void decide(false)}>
                Loại (R)
              </Button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

/** For admins only; the server refuses everyone else, whatever the UI shows. */
export function AdminScreen() {
  const [tab, setTab] = useState<Tab>("queue");
  return (
    <>
      <PageHead title="Quản trị" lead="Duyệt nguồn cho kho chung, theo dõi chỗ thiếu nguồn và chi phí tìm kiếm." />
      <Tabs label="Các mục quản trị" panelId="admin-panel" tabs={[...tabs]} value={tab} onChange={setTab} />
      <div role="tabpanel" id="admin-panel" aria-labelledby={`admin-panel-tab-${tab}`} className="tab-panel">
        {tab === "queue" && <Queue />}
        {tab === "health" && <Health />}
        {tab === "costs" && <Costs />}
      </div>
    </>
  );
}
