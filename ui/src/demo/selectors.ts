// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import { courses } from "./fixtures";
export const courseFor = (id: string) =>
  courses.find((course) => course.id === id)!;
