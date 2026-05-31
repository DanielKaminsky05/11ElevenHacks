# Testing Best Practices

Guidelines for writing and maintaining tests in this project.

## Philosophy

- Tests exist to give confidence that the app behaves correctly and to catch regressions — write them to describe behavior, not implementation details.
- Favor a few high-value tests over many brittle ones. Aim for the testing pyramid: many fast unit tests, fewer integration tests, a small number of end-to-end tests.
- A test that never fails when the code is wrong is worse than no test. Make sure each test can actually fail.

## Structure & Naming

- Co-locate tests with the code they cover (e.g. `Button.tsx` → `Button.test.tsx`) or mirror the source tree under a `__tests__/` or `tests/` directory.
- Name tests by the behavior they assert: `it("disables submit while the form is pending")`, not `it("test1")`.
- Follow the Arrange–Act–Assert pattern and keep each test focused on a single behavior.

## Unit Tests

- Test pure functions and small units in isolation; they should be fast and deterministic.
- Avoid mocking what you don't own where possible — mocking internal implementation makes tests fragile.
- Keep fixtures and factories small and readable; prefer explicit data in the test over hidden shared state.

## Component / Integration Tests

- For React/Next.js components, prefer [Testing Library](https://testing-library.com/) and query by accessible role/label/text rather than test IDs or CSS selectors.
- Test what the user sees and does (click, type, navigate), not internal state or props.
- Use test IDs only as a last resort when no accessible query is available.

## End-to-End Tests

- Reserve E2E (e.g. Playwright/Cypress) for critical user journeys: sign-in, checkout, core flows.
- Keep E2E suites small and stable; they are slow and the most expensive to maintain.
- Run E2E against a realistic environment with seeded, isolated test data.

## Async & Flakiness

- Await UI changes with `findBy*` / `waitFor` instead of fixed `sleep`/timeouts.
- Eliminate shared mutable state between tests; each test should set up and tear down its own data.
- Treat flaky tests as bugs — fix or quarantine them; never ignore intermittent failures.

## Coverage & CI

- Track coverage as a signal, not a target. 100% coverage does not mean correctness.
- Prioritize covering branching logic, edge cases, and error paths over trivial getters.
- Run lint, type checks, and the full test suite in CI on every pull request; keep the suite fast enough that developers run it locally.

## Mocking & Test Data

- Mock network calls at the boundary (e.g. MSW for HTTP) rather than stubbing internal modules.
- Reset mocks between tests to avoid leakage.
- Keep secrets and real credentials out of tests; use clearly fake values.
