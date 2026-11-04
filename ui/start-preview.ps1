# Run this checkout's redesigned app (default mode is the sample-data preview).
Set-Location -LiteralPath $PSScriptRoot
pnpm exec vite --host 127.0.0.1 --port 5173 --strictPort
