import { BackendError } from "./backend";
import type { AssessmentRow, Book, Outcome, SyllabusDraft, Week } from "./core";

/**
 * Rule-based syllabus reading for the GitHub Pages preview, which has no backend.
 * It uses the anchors the server finds before its LLM call (app/syllabus/anchors.py):
 * "Tuần N"/"Week N", percentages and outcome codes, plus the sections of the faculty
 * template (outcomes, teaching plan, assessments, textbooks). The full app still parses
 * with the LLM; this only has to turn a well-formed syllabus into a reviewable draft.
 */

type Section = "outcomes" | "plan" | "assessments" | "textbooks";
// Whole-heading matches: a table cell such as "Assessment A21" must not open a section.
const SECTIONS: [Section, RegExp][] = [
  ["outcomes", /^(?:course |learning )?outcomes$|^chuẩn đầu ra(?: môn học| học phần)?$/i],
  ["plan", /^(?:teaching plan|(?:course )?schedule|lịch trình(?: giảng dạy)?|kế hoạch giảng dạy|nội dung (?:môn học|chi tiết))$/i],
  ["assessments", /^(?:assessments?|grading|evaluation|đánh giá(?: học phần| kết quả)?)$/i],
  ["textbooks", /^(?:textbooks?|references|resources|giáo trình|tài liệu(?: học tập| tham khảo)?)$/i],
];
const WEEK = /\b(?:week|tuần)\s*(\d{1,2})\b/i;
const WEEK_LINE =
  /^(?:week|tuần)\s*(\d{1,2})(?:\s*[-–—]\s*\d{1,2})?\s*[:.)\-–—|]?\s*(.*)$/i;
const ROW_ID = /^(?:(?:week|tuần|buổi|session)\s*)?(\d{1,2})$/i;
const PERCENT = /(\d{1,3}(?:[.,]\d+)?)\s*%/;
// "CLO1: …" anywhere; inside the outcomes section also "G1.1 …" (code, then words).
const CLO_LINE = /^((?:CLO|LO)\s*\d{1,2}(?:\.\d{1,2})?)\s*[:.)\-–—|]\s*(\p{L}.*)$/iu;
const CO_CODE = /^((?:CLO|CO|LO|G)\s*\d{1,2}(?:\.\d{1,2})?)(?:\s*[:.)\-–—|]\s*|\s+)?(\p{L}.*)?$/iu;
const CO_REF = /^(?:CLO|CO|LO|G)\s*\d{1,2}(?:\.\d{1,2})?\b/i; // "G2.1, G2.3" in a plan row
const LEVEL_TAG = /\s+[ITU](?:\/[ITU])*$/; // the I/T/U column after an outcome
const ASSESSMENT =
  /midterm|final|exam|quiz|project|assignment|homework|lab|presentation|participation|attendance|giữa kỳ|cuối kỳ|thi\b|kiểm tra|bài tập|đồ án|thực hành|chuyên cần|báo cáo|thuyết trình/i;
const ASSESSMENT_CODE = /^[A-Z]{1,2}\d{1,3}$/;
const BULLET = /^(?:[-*•·−–]|\d{1,2}[.)]|\[\d{1,2}\])\s*/;
const MAX_TOPICS_PER_WEEK = 8;
const MAX_TEXTBOOKS = 10;

const clean = (value: string) =>
  value.replace(/\s+/g, " ").replace(/^[\s|:–—-]+|[\s|.;,:–—-]+$/g, "");

/** Table cells: PDF columns are 2+ spaces apart, Word tables "a | b", pasted ones tabs. */
const cells = (raw: string) => raw.split(/\s{2,}|\t|\|/).map(clean).filter(Boolean);

function sectionOf(line: string): Section | null | undefined {
  const numbered = line.match(/^(?:\d{1,2}|[IVX]{1,4})\.\s*(.+)$/);
  const text = (numbered ? numbered[1] : line).trim();
  // A wrapped table header ("Course / outcomes") leaves lowercase fragments; headings
  // are numbered or capitalised.
  if (text.length > 40 || (!numbered && !/^\p{Lu}/u.test(text))) return undefined;
  for (const [section, pattern] of SECTIONS) if (pattern.test(text)) return section;
  // Any other numbered capitalised heading ("3. COURSE GOALS") closes the section.
  return numbered && /^[\p{Lu}\s&,]+$/u.test(text) ? null : undefined;
}

/** A schedule table header: an id/week column and a topic column. */
const isPlanHeader = (row: string[]) =>
  row.length > 1 &&
  /^(?:id|no\.?|stt|week|tuần|buổi|session)$/i.test(row[0]) &&
  row.slice(1).some((c) => /^(?:topics?|content|nội dung|chủ đề)/i.test(c));

function topicsOf(text: string): string[] {
  return text
    .split(/[,;•·|]/)
    .map(clean)
    .filter((t) => t && t.length <= 120 && !PERCENT.test(t))
    .slice(0, MAX_TOPICS_PER_WEEK);
}

function assessmentOf(line: string, page: number): AssessmentRow | null {
  const percent = line.match(PERCENT);
  if (!percent || !ASSESSMENT.test(line)) return null;
  const row = cells(line);
  const name = clean(
    (row.length > 1 ? row[0] : line.split(/[:(]|\d{1,3}(?:[.,]\d+)?\s*%/)[0])
      .replace(WEEK, ""),
  );
  const week = line.match(WEEK);
  return {
    name: name || clean(line).slice(0, 60),
    weight: Number(percent[1].replace(",", ".")),
    due_week: week ? Number(week[1]) : null,
    source_page: page,
  };
}

export function parseSyllabusText(
  pages: string[],
  fileName: string,
): SyllabusDraft {
  const lines = pages.flatMap((text, i) =>
    text.split("\n").map((raw) => ({ raw: raw.replace(/\r$/, ""), page: i + 1 })),
  );
  const weeks = new Map<number, Week>();
  const outcomes: Outcome[] = [];
  const assessments: AssessmentRow[] = [];
  const blocks: { code: string; name: string; text: string; page: number }[] = [];
  const planRows: { week: number; text: string }[] = [];
  const textbooks: Book[] = [];
  let title = "";
  let section: Section | null = null;
  let pendingWeek: Week | null = null;
  let outcome: Outcome | null = null;
  let lastRow = 0;
  let planClosed = false;

  const addTopics = (week: number, topics: string[], page: number) => {
    const entry = weeks.get(week) ?? { week, topics: [], source_page: page };
    for (const topic of topics) {
      // The same title in two weeks ("Case study") is two sessions, not one topic.
      const taken = [...weeks.values()].some(
        (w) => w.week !== week && w.topics.some((t) => t.toLowerCase() === topic.toLowerCase()),
      );
      const t = taken ? `${topic} (tuần ${week})` : topic;
      if (!entry.topics.includes(t) && entry.topics.length < MAX_TOPICS_PER_WEEK)
        entry.topics.push(t);
    }
    weeks.set(week, entry);
    return entry;
  };

  // Running headers and footers ("Course Syllabus | … Page 3") repeat on most pages; left
  // in, they would run into whatever table cell wraps across the page break.
  const seen = new Map<string, Set<number>>();
  const key = (raw: string) => clean(raw).replace(/\d+/g, "#");
  for (const { raw, page } of lines)
    if (key(raw)) (seen.get(key(raw)) ?? seen.set(key(raw), new Set()).get(key(raw))!).add(page);
  // A bare number ("3", a table row id) repeats on many pages too, but is content.
  const running = (raw: string) =>
    pages.length >= 3 &&
    /\p{L}{3}/u.test(raw) &&
    (seen.get(key(raw))?.size ?? 0) >= pages.length / 2;

  for (let i = 0; i < lines.length; i++) {
    const { raw, page } = lines[i];
    if (running(raw)) continue;
    const line = clean(raw.replace(/\t+/g, " | "));
    const row = cells(raw);
    if (!line) {
      if (section === "textbooks") section = null;
      continue;
    }
    const named = line.match(/^(?:course name|tên (?:môn học|học phần))\s*:\s*(.+)$/i);
    if (named) title = clean(named[1]);
    else if (!title && page === 1 && line.length <= 120) title = line;

    const heading = sectionOf(line);
    if (heading !== undefined) {
      section = heading;
      outcome = null;
      continue;
    }
    // The assessment table has an "ID | Topic" header too; it stays an assessment table.
    if (isPlanHeader(row) && section !== "assessments") {
      section = "plan";
      continue;
    }

    if (section === "outcomes") {
      const co = line.match(CO_CODE);
      if (co) {
        outcome = { code: co[1].replace(/\s/g, "").toUpperCase(), description: "", source_page: page };
        if (!outcomes.some((o) => o.code === outcome!.code)) outcomes.push(outcome);
        else outcome = null;
        if (outcome && co[2]) outcome.description = clean(co[2].replace(LEVEL_TAG, ""));
        continue;
      }
      // A description wrapped onto the next lines of its table cell.
      if (outcome) outcome.description = clean(`${outcome.description} ${line.replace(LEVEL_TAG, "")}`);
      continue;
    }

    if (section === "assessments") {
      if (row.length && ASSESSMENT_CODE.test(row[0])) {
        blocks.push({ code: row[0], name: row[1] ?? "", text: line, page });
        continue;
      }
      if (blocks.length) {
        blocks[blocks.length - 1].text += ` ${line}`;
        continue;
      }
    }

    if (section === "textbooks") {
      if (TEXTBOOKS_HEADING.test(line)) continue;
      // Built from the raw line so a wrapped entry keeps its commas; cleaned at the end.
      const text = raw.replace(/\s+/g, " ").trim();
      const rest = BULLET.test(text) || !textbooks.length ? text.replace(BULLET, "") : "";
      if (rest && textbooks.length < MAX_TEXTBOOKS)
        textbooks.push({ title: rest, author: "", source_page: page });
      else if (!rest && textbooks.length)
        textbooks[textbooks.length - 1].title += ` ${text}`;
      continue;
    }

    const assessment = assessmentOf(line, page);
    if (assessment) {
      assessments.push(assessment);
      pendingWeek = null;
      continue;
    }
    const clo = line.match(CLO_LINE);
    if (clo) {
      const code = clo[1].replace(/\s/g, "").toUpperCase();
      if (!outcomes.some((o) => o.code === code))
        outcomes.push({ code, description: clean(clo[2]), source_page: page });
      continue;
    }

    const id = section === "plan" && row.length ? row[0].match(ROW_ID) : null;
    if (id) {
      const week = Number(id[1]);
      // A second table restarting at 1 is the lab schedule; the roadmap follows the first.
      if (week <= lastRow) planClosed = true;
      lastRow = week;
      if (planClosed) continue;
      // In PDF text a topic cell wraps over several lines (Word and pasted tables keep a
      // row on one line). Read on until a cell boundary: another column on the line, the
      // trailing space PDF text leaves after a cell, an outcome code or the next row.
      const parts = row.slice(1, 2);
      let j = i;
      const wraps = row.length < 3 && !/[|\t]/.test(raw);
      while (wraps && j + 1 < lines.length && lines[j + 1].page === page) {
        const next = cells(lines[j + 1].raw);
        if (!next.length || CO_REF.test(next[0]) || ROW_ID.test(next[0]) || PERCENT.test(lines[j + 1].raw))
          break;
        j++;
        // Keep the wrapped part's own punctuation ("Theories," / "Thinking:").
        parts.push(lines[j].raw.split(/\s{2,}|\t|\|/).find((c) => c.trim())!.trim());
        if (next.length > 1 || /\s$/.test(lines[j].raw)) break;
      }
      const topic = clean(parts.join(" "));
      if (topic) addTopics(week, [topic.slice(0, 120)], page);
      planRows.push({ week, text: lines.slice(i, j + 1).map((l) => l.raw).join(" ") });
      i = j;
      continue;
    }
    if (section === "plan" && planRows.length) {
      // Later columns of the row: its outcome codes, activities and assessment codes.
      if (!planClosed) planRows[planRows.length - 1].text += ` ${line}`;
      continue;
    }

    const week = line.match(WEEK_LINE);
    if (week) {
      const topics = topicsOf(week[2]);
      const entry = addTopics(Number(week[1]), topics, page);
      // "Tuần 3" alone on its line: its topics follow on the next line.
      pendingWeek = topics.length ? null : entry;
      continue;
    }
    if (TEXTBOOKS_HEADING.test(line) && line.length <= 60) {
      section = "textbooks";
      const rest = clean(line.split(":").slice(1).join(":"));
      if (rest) textbooks.push({ title: rest, author: "", source_page: page });
      continue;
    }
    if (pendingWeek) {
      addTopics(pendingWeek.week, topicsOf(line.replace(BULLET, "")), page);
      pendingWeek = null;
    }
  }

  // Coded assessment tables list a group (A1 30%) and its parts (A11 10%, A12 20%):
  // keep the parts, and date each by the last teaching-plan row that names it.
  for (const b of blocks) {
    if (blocks.some((o) => o.code !== b.code && o.code.startsWith(b.code))) continue;
    const percent = b.text.match(PERCENT);
    if (!percent) continue;
    const named = new RegExp(`\\b${b.code}\\b(?!\\.)`);
    const due = planRows.filter((r) => named.test(r.text)).map((r) => r.week);
    assessments.push({
      name: clean(b.name) || b.code,
      weight: Number(percent[1].replace(",", ".")),
      due_week: due.length ? Math.max(...due) : null,
      source_page: b.page,
    });
  }

  // An exam week without topics gets a review topic, as the reviewed CSC10014 sample has,
  // so the assessment falls inside the schedule the learner confirms.
  for (const a of assessments)
    if (a.due_week && !weeks.get(a.due_week)?.topics.length)
      addTopics(a.due_week, [`Ôn tập: ${a.name}`], a.source_page ?? 1);

  const weekRows = [...weeks.values()]
    .filter((w) => w.topics.length)
    .sort((a, b) => a.week - b.week);
  // The server refuses a document with no week, percentage or outcome anchor (anchors.py).
  if (!weekRows.length && !assessments.length && !outcomes.length)
    throw new BackendError(422, "not_a_syllabus");

  return {
    id: "sy_preview",
    file_name: fileName,
    pages: pages.length,
    raw_text: pages.join("\n\f\n"),
    status: "draft",
    warnings: [],
    course: title ? { title: { value: title, source_page: 1 } } : undefined,
    outcomes: outcomes.filter((o) => o.description),
    weeks: weekRows,
    assessments,
    textbooks: textbooks
      .map((b) => ({ ...b, title: clean(b.title) }))
      .filter((b) => b.title),
    source_pages: Object.fromEntries(
      pages.map((text, i) => [i + 1, text.trim().slice(0, 4000)]),
    ),
  };
}

const TEXTBOOKS_HEADING = /^(?:textbooks?|references|giáo trình|tài liệu tham khảo)\b/i;

/** One string per page: form feeds split pasted text, PDFs keep their pages. */
export async function readPages(input: File | string): Promise<string[]> {
  if (typeof input === "string") return input.split("\f");
  const pages = /\.pdf$/i.test(input.name)
    ? await pdfPages(input)
    : (await docxText(input)).split("\f");
  // A scanned PDF has pages but no text layer; the full app refuses it the same way.
  if (!pages.some((p) => p.trim())) throw new BackendError(422, "scanned_pdf");
  return pages;
}

async function pdfPages(file: File): Promise<string[]> {
  // Loaded only when a PDF is chosen, so the preview bundle stays small.
  const [pdfjs, worker] = await Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
  ]);
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  const doc = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise;
  const pages: string[] = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const content = await (await doc.getPage(n)).getTextContent();
    pages.push(
      content.items
        .map((item) => ("str" in item ? item.str + (item.hasEOL ? "\n" : " ") : ""))
        .join(""),
    );
  }
  return pages;
}

/** word/document.xml of a .docx as text: paragraphs are lines, table cells "a | b". */
export async function docxText(file: Blob): Promise<string> {
  const xml = await unzipEntry(await file.arrayBuffer(), "word/document.xml");
  return xml
    .replace(/<w:tr[\s\S]*?<\/w:tr>/g, (row) =>
      row.replace(/<\/w:p>/g, " ").replace(/<\/w:tc>/g, " | ") + "\n",
    )
    .replace(/<w:br [^>]*w:type="page"[^>]*\/>/g, "\f")
    .replace(/<w:tab\/>/g, "\t")
    .replace(/<\/w:p>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&(amp|lt|gt|quot|apos);/g, (_, e: string) =>
      ({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" })[e]!,
    );
}

/** Read one entry of a zip through its central directory (local headers may omit sizes). */
async function unzipEntry(buffer: ArrayBuffer, name: string): Promise<string> {
  const view = new DataView(buffer);
  let end = buffer.byteLength - 22;
  while (end >= 0 && view.getUint32(end, true) !== 0x06054b50) end--;
  if (end < 0) throw new BackendError(415, "unsupported_type");
  let at = view.getUint32(end + 16, true);
  const decoder = new TextDecoder();
  for (let i = 0; i < view.getUint16(end + 10, true); i++) {
    const method = view.getUint16(at + 10, true);
    const size = view.getUint32(at + 20, true);
    const nameLength = view.getUint16(at + 28, true);
    const skip = nameLength + view.getUint16(at + 30, true) + view.getUint16(at + 32, true);
    const local = view.getUint32(at + 42, true);
    if (decoder.decode(new Uint8Array(buffer, at + 46, nameLength)) === name) {
      const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
      const data = new Uint8Array(buffer, start, size);
      if (method === 0) return decoder.decode(data);
      const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      return new Response(stream).text();
    }
    at += 46 + skip;
  }
  throw new BackendError(415, "unsupported_type");
}
