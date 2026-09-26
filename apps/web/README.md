# web

The Next.js (App Router, TypeScript strict) front end on port 3000: the live run view at `/`, a past run at `/runs/[id]`, and a diff between runs at `/runs/[id]/diff/[other]`. All UI state is a pure fold of the API's event stream in `lib/reducer.ts`, read through `lib/selectors.ts`; the map is MapLibre with the OpenFreeMap style configured in `lib/config.ts`. Run it with `pnpm --filter web dev` or `make dev`; tests use vitest.
