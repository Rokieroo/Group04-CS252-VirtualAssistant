// @vitest-environment node
// Node's Blob, Response and DecompressionStream read the .docx like a browser does.
import { describe, expect, it } from "vitest";
import { docxText, parseSyllabusText, readPages } from "./demoParser";
import { computeMilestoneScope, normalizeGraph } from "./graph";
import { roadmapFrom } from "./mockCore";
import { validateDraft } from "./syllabus";

const ENGLISH = `CS101 Data Structures
CLO1: Implement linear data structures
CLO2: Analyse algorithm complexity
Week 1: Arrays, linked lists
Week 2: Stacks and queues
Week 3
Trees; binary search trees
Assessment
Midterm exam: week 4 (40%)
Final exam - week 8 - 60%
Textbooks
1. Introduction to Algorithms, Cormen
2. Data Structures in C`;

describe("parseSyllabusText", () => {
  it("reads weeks, outcomes, weighted assessments and textbooks from pasted text", () => {
    const draft = parseSyllabusText([ENGLISH], "pasted");
    expect(draft.course?.title.value).toBe("CS101 Data Structures");
    expect(draft.weeks).toEqual([
      { week: 1, topics: ["Arrays", "linked lists"], source_page: 1 },
      { week: 2, topics: ["Stacks and queues"], source_page: 1 },
      { week: 3, topics: ["Trees", "binary search trees"], source_page: 1 },
      { week: 4, topics: ["Ôn tập: Midterm exam"], source_page: 1 },
      { week: 8, topics: ["Ôn tập: Final exam"], source_page: 1 },
    ]);
    expect(draft.outcomes.map((o) => o.code)).toEqual(["CLO1", "CLO2"]);
    expect(draft.assessments).toEqual([
      { name: "Midterm exam", weight: 40, due_week: 4, source_page: 1 },
      { name: "Final exam", weight: 60, due_week: 8, source_page: 1 },
    ]);
    expect(draft.textbooks.map((b) => b.title)).toEqual([
      "Introduction to Algorithms, Cormen",
      "Data Structures in C",
    ]);
    expect(validateDraft(draft).filter((w) => w.blocking)).toEqual([]);
  });

  it("reads Vietnamese anchors and a tab-separated week table, keeping page numbers", () => {
    const draft = parseSyllabusText(
      [
        "Nhập môn tư duy tính toán\nCLO1: Phát biểu bài toán",
        "Tuần\tNội dung\n1\tPhân rã bài toán\n2\tTrừu tượng hóa, mẫu hình\nGiữa kỳ: tuần 8 (30%)\nCuối kỳ: tuần 15 (70%)",
      ],
      "de-cuong.pdf",
    );
    expect(draft.pages).toBe(2);
    expect(draft.weeks).toEqual([
      { week: 1, topics: ["Phân rã bài toán"], source_page: 2 },
      // A table cell is one topic, commas and all.
      { week: 2, topics: ["Trừu tượng hóa, mẫu hình"], source_page: 2 },
      { week: 8, topics: ["Ôn tập: Giữa kỳ"], source_page: 2 },
      { week: 15, topics: ["Ôn tập: Cuối kỳ"], source_page: 2 },
    ]);
    expect(draft.assessments.map((a) => [a.name, a.weight, a.due_week])).toEqual([
      ["Giữa kỳ", 30, 8],
      ["Cuối kỳ", 70, 15],
    ]);
    expect(draft.source_pages?.[2]).toContain("Phân rã bài toán");
  });

  it("reads the faculty template as pdf.js extracts it (CSC10014)", () => {
    // pdf.js text: columns 2+ spaces apart, a trailing space after a table cell, wrapped
    // cells on their own lines, and the running header on every page.
    const header = "VNUHCM-UNIVERSITY OF SCIENCE \nCourse Syllabus |   Computational Thinking   Page ";
    const draft = parseSyllabusText(
      [
        `${header}1 \nCOURSE SYLLABUS \nCourse name:   Computational Thinking \n3.   COURSE GOALS \nG1   Introduce the foundations \n4.   COURSE OUTCOMES \nCO   Description   I/T/U \nG1.1   Identify the key pillars of Computational \nThinking (CT).   I \nG2.1 \nAnalyze ill-defined problems.   T/U `,
        `${header}2 \n5.   TEACHING PLAN \nTHEORY \nID   Topic   Course\noutcomes \nActivities (samples)   Assessments \n1 \nFoundations of\nComputational\nThinking: Theories, \nG1.1, G1.2 \nLecturing \nQ&A, Group discussion   A11 \n2   Case study   G2.1 \nDiscussion &\nAssessment   A21 \n3   Algorithm design & \nFlowchart   G4.1 \nA11, A21 \n4   Case study   G2.3 \nA22 \nLABORATORY \nID   Topic   Course\n1 \nTeam formation \n`,
        `${header}3 \n6.   ASSESSMENTS \nID   Topic   Description   Course\noutcomes   Ratio (%) \nA1   Assignments   30% \nA11   Weekly Quizzes   In-class quiz \n30% \nA2   Projects   70% \nA21   Proposal   40% \nA22   Final product   30% \n7.   RESOURCES \nTextbooks \n−   Applied Computational Thinking with Python, \nPackt Publishing \n8.   GENERAL   REGULATIONS \n−   Attendance is required. `,
      ],
      "Syllabus.pdf",
    );
    expect(draft.course?.title.value).toBe("Computational Thinking");
    expect(draft.outcomes.map((o) => [o.code, o.description])).toEqual([
      ["G1.1", "Identify the key pillars of Computational Thinking (CT)"],
      ["G2.1", "Analyze ill-defined problems"],
    ]);
    // The lab table restarts at 1 and is left out; "Case study" twice is two sessions.
    expect(draft.weeks.map((w) => [w.week, w.topics])).toEqual([
      [1, ["Foundations of Computational Thinking: Theories"]],
      [2, ["Case study"]],
      [3, ["Algorithm design & Flowchart"]],
      [4, ["Case study (tuần 4)"]],
    ]);
    // Group rows (A1, A2) give way to their parts, dated by the last plan row naming them.
    expect(draft.assessments.map((a) => [a.name, a.weight, a.due_week])).toEqual([
      ["Weekly Quizzes", 30, 3],
      ["Proposal", 40, 3],
      ["Final product", 30, 4],
    ]);
    expect(draft.textbooks.map((b) => b.title)).toEqual([
      "Applied Computational Thinking with Python, Packt Publishing",
    ]);
    expect(validateDraft(draft).filter((w) => w.blocking)).toEqual([]);
  });

  it("refuses text with no week, percentage or CLO, like the server", () => {
    expect(() => parseSyllabusText(["Dear team, lunch is at noon."], "x")).toThrow(
      expect.objectContaining({ code: "not_a_syllabus" }),
    );
  });
});

describe("readPages", () => {
  it("splits pasted text on form feeds", async () => {
    expect(await readPages("Week 1: A\fWeek 2: B")).toEqual(["Week 1: A", "Week 2: B"]);
  });

  it("reads a deflated .docx: paragraphs become lines and table cells a | b", async () => {
    const xml =
      '<w:document><w:body><w:p><w:r><w:t>CS101 &amp; Labs</w:t></w:r></w:p>' +
      "<w:tbl><w:tr><w:tc><w:p><w:t>Week</w:t></w:p></w:tc><w:tc><w:p><w:t>Topic</w:t></w:p></w:tc></w:tr>" +
      "<w:tr><w:tc><w:p><w:t>1</w:t></w:p></w:tc><w:tc><w:p><w:t>Arrays</w:t></w:p></w:tc></w:tr></w:tbl>" +
      "</w:body></w:document>";
    const text = await docxText(await zip("word/document.xml", xml));
    expect(text).toContain("CS101 & Labs\n");
    const draft = parseSyllabusText(text.split("\f"), "s.docx");
    expect(draft.weeks).toEqual([{ week: 1, topics: ["Arrays"], source_page: 1 }]);
  });
});

describe("roadmapFrom", () => {
  it("links weeks in order and makes each milestone cover the topics before it", () => {
    const roadmap = roadmapFrom(parseSyllabusText([ENGLISH], "pasted"));
    const title = (id: string) => roadmap.nodes.find((n) => n.id === id)!.title;
    expect(roadmap.edges.map((e) => [title(e.parent_id), title(e.child_id), e.kind])).toEqual([
      ["linked lists", "Stacks and queues", "soft"],
      ["Stacks and queues", "Trees", "soft"],
      ["binary search trees", "Ôn tập: Midterm exam", "soft"],
      ["Ôn tập: Midterm exam", "Ôn tập: Final exam", "soft"],
    ]);
    const midterm = roadmap.nodes.find((n) => n.title === "Midterm exam")!;
    expect(midterm.covers!.map(title)).toEqual([
      "Arrays", "linked lists", "Stacks and queues", "Trees", "binary search trees",
      "Ôn tập: Midterm exam",
    ]);
    // Built as CoreJourney's preview graph is.
    const graph = normalizeGraph({
      nodes: roadmap.nodes.map((n) => ({ ...n, est_minutes: n.est_minutes ?? undefined })),
      edges: roadmap.edges,
    });
    // The milestone, its six topics, and nothing after week 4.
    expect(computeMilestoneScope(midterm.id, graph.nodes, graph.edges).size).toBe(7);
  });
});

/** A one-entry zip with a deflated entry, as Word writes it. */
async function zip(name: string, content: string): Promise<Blob> {
  const raw = new TextEncoder().encode(content);
  const data = new Uint8Array(
    await new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream("deflate-raw"))).arrayBuffer(),
  );
  const file = new TextEncoder().encode(name);
  const header = (signature: number, size: number) => {
    const view = new DataView(new ArrayBuffer(size));
    view.setUint32(0, signature, true);
    return view;
  };
  const local = header(0x04034b50, 30);
  local.setUint16(8, 8, true);
  local.setUint32(18, data.length, true);
  local.setUint32(22, raw.length, true);
  local.setUint16(26, file.length, true);
  const central = header(0x02014b50, 46);
  central.setUint16(10, 8, true);
  central.setUint32(20, data.length, true);
  central.setUint32(24, raw.length, true);
  central.setUint16(28, file.length, true);
  central.setUint32(42, 0, true);
  const centralAt = 30 + file.length + data.length;
  const end = header(0x06054b50, 22);
  end.setUint16(8, 1, true);
  end.setUint16(10, 1, true);
  end.setUint32(12, 46 + file.length, true);
  end.setUint32(16, centralAt, true);
  return new Blob([local.buffer, file, data, central.buffer, file, end.buffer]);
}
