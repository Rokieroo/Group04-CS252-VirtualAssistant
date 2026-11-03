import { expect, it } from "vitest";
import type {
  Assessment,
  LearningOutcome,
  Roadmap,
  CostReport,
  CostTotals,
  DailyCost,
  NodeCost,
  ProviderUsage,
  RoadmapNode,
  Syllabus,
} from "./types";

type Schemas = Record<string, { properties: Record<string, unknown> }>;
const [contract] = Object.values(
  import.meta.glob("../../../docs/openapi.json", { eager: true, import: "default" }),
) as { components: { schemas: Schemas } }[];

// One value per type: TypeScript rejects a missing or extra key, and the test
// compares the keys with the backend's response schema of the same name.
const samples = {
  SyllabusOut: {
    id: "",
    syllabus_id: "",
    course_id: "",
    raw_text: "",
    created_at: "",
    learning_outcomes: [],
    assessments: [],
  } satisfies Syllabus,
  LearningOutcomeOut: {
    id: "",
    syllabus_id: "",
    code: "",
    description: "",
    bloom_level: "",
  } satisfies LearningOutcome,
  AssessmentOut: {
    id: "",
    syllabus_id: "",
    name: "",
    weight: 0,
    due_week: null,
  } satisfies Assessment,
  RoadmapOut: {
    id: "",
    roadmap_id: "",
    course_id: "",
    user_id: "",
    title: "",
    created_at: "",
    nodes: [],
  } satisfies Roadmap,
  RoadmapNodeOut: {
    id: "",
    roadmap_id: "",
    type: "topic",
    kind: null,
    title: "",
    week: null,
    duration_minutes: null,
    est_minutes: null,
    due_at: null,
    covers: [],
  } satisfies RoadmapNode,
  CostReport: {
    days: 7,
    since: "",
    totals: {} as CostTotals,
    nodes: [],
    providers: [],
    daily: [],
  } satisfies CostReport,
  CostTotals: {
    searches: 0,
    cache_hits: 0,
    llm_calls: 0,
    llm_calls_today: 0,
    llm_cost_usd: 0,
    search_cost_usd: 0,
    cost_usd: 0,
    cost_per_search_usd: 0,
  } satisfies CostTotals,
  NodeCost: {
    node_id: null,
    node_title: "",
    searches: 0,
    cache_hits: 0,
    llm_calls: 0,
    llm_cost_usd: 0,
    search_cost_usd: 0,
    cost_usd: 0,
    last_search_at: "",
  } satisfies NodeCost,
  ProviderUsage: {
    provider: "",
    calls: 0,
    errors: 0,
    calls_today: 0,
    avg_latency_ms: 0,
    max_latency_ms: 0,
    cost_usd: 0,
  } satisfies ProviderUsage,
  DailyCost: { day: "", searches: 0, cost_usd: 0 } satisfies DailyCost,
};

it.each(Object.entries(samples))("%s matches docs/openapi.json", (name, sample) => {
  const schema = contract.components.schemas[name];
  expect(schema, `${name} is missing from docs/openapi.json`).toBeDefined();
  expect(Object.keys(sample).sort()).toEqual(Object.keys(schema.properties).sort());
});
