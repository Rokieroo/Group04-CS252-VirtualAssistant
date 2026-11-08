# S3–S5 UI review (#56, #57)

Run the spec-shaped UI preview from `ui/`:

```powershell
$env:VITE_BACKEND_MODE='core-mock'
pnpm dev
```

Use the CSC10014 fixture via the file picker, or paste text. The mock exercises S3 upload, S4 editing and confirmation, S5 roadmap and scheduling navigation without a server. The six screenshots here cover desktop 1440×900 and mobile 390×844.

The syllabus setup stays inside Courses: upload → review → proposed roadmap → explicit confirmation. The completion screen offers Return to Courses and View roadmap. The live API is called to persist the roadmap only after confirmation. `desktop-proposal.png` and `mobile-proposal.png` show the approval stage.

The live `VITE_BACKEND_MODE=api` path uses the existing syllabus and roadmap endpoints. Current backend gaps: syllabus PDF/DOCX upload, structured weeks/textbooks, page text/citations, and persisted prerequisite edges. The UI states these limits where they apply. The mock is kept separate from the live API.
