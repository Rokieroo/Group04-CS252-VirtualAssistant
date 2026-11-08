import { describe, expect, it } from "vitest";
import {
  addPrereq,
  checkFile,
  createsCycle,
  merge,
  remove,
  removePrereq,
  MAX_UPLOAD_BYTES,
  type Concept,
  type Graph,
} from "./concepts";

const c = (id: string, pages: number[]): Concept => ({
  id,
  slug: id,
  title: id.toUpperCase(),
  summary: "",
  bloom_level: "understand",
  source_file: "w1.pdf",
  source_pages: pages,
  confirmed: false,
});
const edge = (parent_id: string, child_id: string) => ({
  parent_id,
  child_id,
  kind: "strict" as const,
  confidence: 1,
});
const graph: Graph = {
  concepts: [c("a", [1]), c("b", [3, 2]), c("c", [5])],
  prereqs: [edge("a", "b"), edge("b", "c")],
};

describe("checkFile", () => {
  it("accepts a PDF up to 20 MB", () => {
    expect(checkFile({ name: "w1.pdf", size: MAX_UPLOAD_BYTES, type: "application/pdf" })).toBeNull();
  });
  it("accepts Word, slides and photos of material (#114)", () => {
    for (const name of ["notes.docx", "week2.PPTX", "board.jpg", "board.jpeg", "board.png"])
      expect(checkFile({ name, size: 10, type: "" })).toBeNull();
  });
  it("rejects other formats", () => {
    for (const name of ["notes.txt", "sheet.xlsx", "anim.gif", "pdf"])
      expect(checkFile({ name, size: 10, type: "application/pdf" })).toBe("not_pdf");
  });
  it("rejects files over 20 MB", () => {
    expect(checkFile({ name: "w1.pdf", size: MAX_UPLOAD_BYTES + 1, type: "application/pdf" })).toBe(
      "file_too_large",
    );
  });
});

describe("concept editing", () => {
  it("merges pages and reroutes edges without self-loops", () => {
    const g = merge(graph, "a", "b");
    expect(g.concepts.map((x) => x.id)).toEqual(["a", "c"]);
    expect(g.concepts[0].source_pages).toEqual([1, 2, 3]);
    expect(g.prereqs).toEqual([edge("a", "c")]);
  });
  it("removes a concept with its edges", () => {
    expect(remove(graph, "b").prereqs).toEqual([]);
  });
});

describe("prerequisite cycles", () => {
  it("detects direct, indirect and self cycles", () => {
    expect(createsCycle(graph.prereqs, "b", "a")).toBe(true);
    expect(createsCycle(graph.prereqs, "c", "a")).toBe(true);
    expect(createsCycle(graph.prereqs, "a", "a")).toBe(true);
    expect(createsCycle(graph.prereqs, "a", "c")).toBe(false);
  });
  it("blocks a cycle-making edge and adds a safe one", () => {
    expect(addPrereq(graph, "c", "a")).toHaveProperty("error");
    const ok = addPrereq(graph, "a", "c");
    expect("prereqs" in ok && ok.prereqs).toContainEqual(edge("a", "c"));
  });
  it("removing an edge unblocks the loop it caused", () => {
    const g = removePrereq(graph, "b", "c");
    expect(g.prereqs).toEqual([edge("a", "b")]);
    expect(addPrereq(g, "c", "a")).toHaveProperty("prereqs");
  });
});
