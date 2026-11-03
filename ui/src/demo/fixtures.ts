import type { Course, State } from "./domain";
import { addDays, dateKey, today } from "../time";

export const courses: Course[] = [
  {
    id: "math",
    name: "Mathematics 7",
    category: "Mathematics",
    description:
      "Build strong foundations in algebra, geometry, and problem solving.",
    prerequisite: "Grade 6 Math basics",
    weeks: 12,
    level: "Beginner",
    color: "purple",
    topics: ["Integers and operations", "Fractions", "Algebra basics"],
  },
  {
    id: "english",
    name: "English foundations",
    category: "Languages",
    description: "Grammar, listening, vocabulary, and everyday conversation.",
    prerequisite: "No prerequisites",
    weeks: 8,
    level: "Beginner",
    color: "green",
    topics: ["Past simple & past continuous", "Vocabulary", "Listening"],
  },
  {
    id: "physics12",
    name: "Physics 12",
    category: "Sciences",
    description: "Mechanics, oscillations, waves, and exam-oriented practice.",
    prerequisite: "Physics 11",
    weeks: 14,
    level: "Advanced",
    color: "amber",
    topics: ["Oscillations", "Waves", "Electricity"],
  },
  {
    id: "python",
    name: "Introduction to Python",
    category: "Technology",
    description:
      "Programming basics through short guided practice and projects.",
    prerequisite: "No prerequisites",
    weeks: 10,
    level: "Beginner",
    color: "purple",
    topics: ["Variables and types", "Loops", "Functions"],
  },
  {
    id: "physics",
    name: "Physics 7",
    category: "Sciences",
    description: "Discover measurement, motion, and the world around you.",
    prerequisite: "Grade 6 Science basics",
    weeks: 12,
    level: "Beginner",
    color: "green",
    topics: ["Measurements", "Motion", "Forces"],
  },
  {
    id: "history",
    name: "History pathway",
    category: "Humanities",
    description: "A six-month path from History 7 to History 8 and History 9.",
    prerequisite: "Begin with History 7",
    weeks: 24,
    level: "Progressive",
    color: "amber",
    topics: ["Early societies", "Ancient civilizations", "Historical sources"],
  },
  {
    id: "biology",
    name: "Biology 9",
    category: "Sciences",
    description: "Explore cells, genetics, and living systems.",
    prerequisite: "Biology 8",
    weeks: 12,
    level: "Intermediate",
    color: "green",
    topics: ["Cells", "Genetics", "Ecosystems"],
  },
];

export const initialState = (): State => {
  const d = today();
  const monday = addDays(d, -((d.getDay() + 6) % 7));
  return {
    version: 2,
    scheduleDate: dateKey(d),
    active: ["english"],
    future: [],
    verified: [],
    name: "Alex",
    hours: 12,
    messages: [
      {
        role: "assistant",
        text: "Let's build your learning roadmap. Tell me what you want to learn, or choose one of the examples below. I can propose courses, review your workload, and help you plan your next step.",
      },
    ],
    sessions: [
      ...["Vocabulary", "Listening", "Past tenses", "Speaking", "Revision"].map(
        (title, i) => ({
          id: `seed-${i}`,
          courseId: "english",
          title,
          date: dateKey(addDays(monday, [0, 1, 2, 5, 6][i])),
          time: ["09:00", "14:00", "09:00", "10:00", "15:00"][i],
          minutes: 45,
          kind: "lesson" as const,
          status: "planned" as const,
        }),
      ),
      {
        id: "past",
        courseId: "english",
        title: "Past simple & past continuous",
        date: dateKey(d),
        time: "09:00",
        minutes: 60,
        kind: "lesson",
        status: "planned",
      },
      {
        id: "quiz",
        courseId: "english",
        title: "Practice & short knowledge check",
        date: dateKey(d),
        time: "16:00",
        minutes: 20,
        kind: "quiz",
        status: "planned",
      },
    ],
  };
};
