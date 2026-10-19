# Code Review Checklist (P4)

A tailored 20-item checklist derived from software engineering antipatterns for an asyncio FastAPI application.

1. **hiding-exceptions**: Never silence exceptions with bare `except: pass` or catch without logging/reraising (applies to workflow, API and voice event handling).
2. **broad-exceptions**: Do not catch generic `Exception` when a specific error (e.g. `openai.RateLimitError`, `TimeoutError`) should be targeted (applies to retry loops and error boundaries).
3. **swallowed-task-exceptions**: Every `asyncio.create_task` must either be awaited, have an error-logging done-callback, or have its result retrieved to prevent unhandled background crashes.
4. **unconstrained-defensive-programming**: Avoid masking bugs by returning dummy/fallback values deep inside logic instead of failing fast or handling at the top boundary.
5. **reraise-without-traceback**: When re-raising or transforming exceptions, use `raise ... from err` or plain `raise` to preserve the original traceback.
6. **undeterministic-tests**: Tests must not rely on real wall-clock sleeps, race conditions, or unseeded random values (mock clocks/sleeps, use seeded simulator).
7. **testing-the-mock**: Verify real system behaviour and output invariants rather than checking that an arbitrary mock was called.
8. **assertions-in-loop**: Avoid placing assertions only inside loops that may not execute; verify sequence length or existence first.
9. **over-reliance-on-centralized-fixtures**: Keep test setups explicit and local where possible so changing a fixture does not break unrelated tests.
10. **late-returns**: Return early on guard conditions to keep nesting flat and cognitive load low.
11. **opaque-function-arguments**: Use explicit typed parameters or Pydantic models instead of untyped `*args`, `**kwargs`, or loose dicts across module boundaries.
12. **magic-numbers**: Define domain thresholds, timeouts, and limits as named constants next to their usage instead of inline raw literals.
13. **inconsistent-verbs**: Use consistent naming conventions (`get_` for single item / lookup, `find_` or `detect_` for collections / scans).
14. **repeating-class-in-method**: Avoid redundant method naming like `Class.get_class()` when `Class.get()` is clearer.
15. **hiding-formatting**: Keep message or string formatting close to where it is consumed rather than scattering trivial one-liner helpers.
16. **returning-none-instead-of-not-found**: In lookup functions expecting an item to exist by id, raise an explicit exception or return typed Optional where absence is valid.
17. **bloated-utils-module**: Keep utilities focused and co-located with their domain (e.g., `retry.py`, `clock.py`) rather than dumping everything into a catch-all `utils.py`.
18. **dead-code**: Remove unused imports, uncalled functions, stale commented-out code, and unused function arguments.
19. **untyped-public-functions**: Public functions, handlers, and endpoints must have complete, clear type annotations.
20. **resource-leaks**: Ensure all open client sessions, WebSocket connections, and background tasks are cleanly closed or cancelled on shutdown.
