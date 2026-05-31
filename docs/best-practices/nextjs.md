# Next.js Best Practices

Guidelines for building and maintaining the Next.js frontend in this project.

## Project Structure

- Use the App Router (`app/`) for new work; keep route segments small and colocate route-specific components, loading, and error UI.
- Keep shared, reusable components in a top-level `components/` directory and feature-specific components close to their routes.
- Put pure helpers in `lib/` and keep them free of React/Next imports so they stay testable.

## Server vs. Client Components

- Default to Server Components. Only add `"use client"` when you need state, effects, refs, or browser-only APIs.
- Push `"use client"` boundaries as far down the tree as possible to keep most of the tree on the server.
- Never import server-only code (secrets, DB clients) into client components.

## Data Fetching

- Fetch data in Server Components using `async`/`await` rather than client-side effects when possible.
- Use the built-in `fetch` caching options (`cache`, `next.revalidate`) deliberately; document why a route opts in or out of caching.
- Co-locate data fetching with the component that needs it; avoid prop-drilling fetched data through many layers.

## Rendering & Performance

- Prefer static rendering; reach for dynamic rendering only when the data is request-specific.
- Use `next/image` for images and `next/font` for fonts to get automatic optimization.
- Use `<Suspense>` with streaming to render meaningful content quickly.
- Lazy-load heavy client components with `next/dynamic`.

## Routing & Navigation

- Use the `<Link>` component for internal navigation to enable prefetching.
- Use route groups `(group)` for organization without affecting the URL.
- Handle loading and error states with `loading.tsx` and `error.tsx` per segment.

## Environment & Config

- Only expose variables prefixed with `NEXT_PUBLIC_` to the browser; keep everything else server-side.
- Validate environment variables at startup so misconfiguration fails fast.

## Code Quality

- Keep TypeScript `strict` mode on and avoid `any`.
- Run lint and type checks before committing.
- Write components that are accessible by default (semantic HTML, labels, keyboard support).
