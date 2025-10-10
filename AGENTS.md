# Memory Hack Contribution Guidelines

This repository hosts the Memory Hack trainer application. It bundles a Falcon
WSGI backend (Python 3.11), a web UI rendered from `app/resources`, and
platform-specific helpers for Windows, Linux, and Steam Deck installs.
The guidance below applies to the entire project unless a more specific
`AGENTS.md` is introduced inside a subdirectory.

## General expectations
- Follow Python's PEP 8 style guide with 4-space indentation. Match the
  existing convention of double-quoted strings unless a single-quoted string
  improves readability (e.g., contains many double quotes).
- Prefer small, testable functions. Shared behaviour should live in
  `app/helpers` rather than re-implementing logic in individual services or
  scripts.
- Avoid adding third-party dependencies unless strictly required. If you must
  add one, document why in `README.md` and ensure it works on all supported
  platforms.
- Keep commits focused and clearly explain any behavioural change in the PR
  body (include manual verification steps when automated tests are unavailable).

## Backend (Falcon / Python)
- The backend follows a service registry pattern via `app.helpers.data_store`.
  Reuse this pattern when introducing new background services.
- Use the `logging` module instead of `print` for diagnostic output. Configure
  loggers at module scope (`logger = logging.getLogger(__name__)`).
- Respect existing threading/locking behaviour in services such as the searcher
  (`app/services/searcher.py`). Acquire the relevant locks before mutating
  shared state.
- Keep request handlers (`on_get`, `on_post`, etc.) lean. Put heavy logic into
  helper/service classes and return JSON using `resp.media` or HTML templates via
  `DynamicHTML`.
- When adjusting installation helpers (`app/patches`, `InstallMemoryHack.desktop`),
  verify the change still supports Windows, Linux, and Steam Deck workflows.

## Front-end (HTML/CSS/JS)
- UI templates live in `app/resources/*.html` and static assets under
  `app/resources/static`. Continue using Onsen UI components and jQuery helpers
  already in place; do not introduce new frameworks.
- Keep JavaScript modular by extending the existing controller objects (e.g.,
  `search`, `codelist`, `aob`, `script`). Place shared behaviour in
  `app/resources/static/custom` when possible.
- Minimise inline styling. Prefer editing the CSS in `app/resources/static/custom`
  or adding a new scoped stylesheet when necessary.
- When altering UI flows, update relevant documentation or screenshots under
  `docs/` so they match the new behaviour.

## Documentation & versioning
- Update `README.md` and any installation instructions under `docs/` whenever
  you change user-facing behaviour or setup steps.
- Bump `app/version.py` when delivering a release-worthy feature or fix.
- New scripts or manual procedures should be recorded in `docs/` (create a new
  markdown file if needed).

## Testing
- There is currently no automated test suite. If you introduce backend logic,
  add targeted unit tests under `tests/` and run them with
  `python -m unittest discover -s tests`.
- For changes affecting the live server, manually verify the app starts with
  `python memory_hack.py` and exercise the modified flow in a browser.
- Document any manual test steps and outcomes in the PR body so reviewers can
  replicate them.
