# Fetchit Terminal App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a polished full-screen downloader and fix verified CLI defects without adding Python dependencies.

**Architecture:** Keep command construction, persistence, and argparse separate from screen rendering. Introduce a managed subprocess worker and terminal-independent form/navigation state; curses consumes their events on its main thread. Preserve prompt fallback and direct commands.

**Tech Stack:** Python standard library, curses, unittest, system yt-dlp and ffmpeg.

**Spec:** ../specs/2026-10-14-terminal-app-design.md

## Global Constraints

- Retain its standard-library-only Python setup with system yt-dlp and ffmpeg.
- Noninteractive CLI commands continue to work without curses initialization.
- Run one yt-dlp command at a time, including its playlist or multi-target behavior.
- Only the UI thread draws.
- Output buffering is bounded.
- No unrelated feature expansion, system configuration changes, or automatic dependency installation.
- Do not initialize or replace Git metadata as part of this UI work.
- The terminal is restored on every exit path.

## Review Focus

- Flags interleaved with multiple URLs must parse without silently losing options (Task 2).
- Pasted Unicode and terminal control characters must not corrupt drawing (Task 4).
- Cancellation during subprocess startup or postprocessing must reap the process (Task 3).
- A failed search producing partial output must show failure rather than launch a download (Task 3).
- Very small windows and resize events must retain form input and avoid drawing errors (Task 5).

## File Structure

- Modify fetchit/config.py and fetchit/history.py: validated and atomic local persistence.
- Modify fetchit/core.py: side-effect-free command construction and reliable direct execution.
- Modify fetchit/cli.py: correct parsing, search dispatch, error handling, terminal mode selection.
- Modify fetchit/ui.py: preserve and repair prompt fallback.
- Create fetchit/jobs.py: managed search/download subprocess events and cancellation.
- Create fetchit/tui_state.py: fields, navigation, screen state, option conversion.
- Create fetchit/tui.py: curses rendering and event loop.
- Create tests/test_persistence.py, test_cli.py, test_core.py, test_jobs.py, test_tui_state.py, test_tui.py: standard-library regression and interface coverage.
- Modify README.md: actual launch behavior, controls, dependency notes, command examples.

### Task 1: Safe persisted defaults and history

**Interfaces:** config.validate_config(cfg: dict) -> dict returns normalized recognized fields with unknown keys preserved; load_config() -> dict and save_config(cfg: dict) -> None retain their interfaces. history._load() -> list[dict], show(limit: int = 20) -> str, add(url: str, title: str = '', status: str = 'ok', extra: dict | None = None) -> None retain their interfaces.

- [x] Add tests/test_persistence.py with temporary paths: null output_dir and numeric quality fall back to DEFAULTS; negative retries/concurrency fall back; non-object history rows are skipped; limit zero returns no records and negative limits are rejected; invalid JSON does not crash.
- [x] Run `python3 -m unittest discover -s tests -p test_persistence.py -v`; verify the malformed-state tests fail on current code.
- [x] Implement config.validate_config in fetchit/config.py, using recognized field type/value checks. Save config and history through a temporary sibling file and os.replace; cleanup failed writes. Propagate actionable write errors rather than suppressing them in persistence helpers.
- [x] Add a write-failure test asserting the previous valid file survives; verify all persistence tests pass with the same command.

### Task 2: Correct CLI command behavior

**Interfaces:** cli.build_parser() -> argparse.ArgumentParser; cli.main(argv=None) -> int; core.build_command(args, cfg: dict) -> list[str]; core.run(cmd: list[str], dry_run: bool = False) -> int remain public. core.validate_options(args, cfg: dict) -> None raises ValueError for invalid effective options.

- [x] Add tests/test_cli.py and tests/test_core.py: URL followed by -q 720 sets quality; two URLs with intervening flags survive; bare -- passes yt-dlp arguments exactly; dry-run creates no output folder or history; invalid quality/container/numeric ranges give a concise error; missing executable returns an error code.
- [x] Run `python3 -m unittest discover -s tests -p 'test_c*.py' -v`; inspect the expected failures before changes.
- [x] Remove redundant argparse remainder; preserve explicit splitting at bare -- and use intermixed parsing for positional URLs. Add conflicting-flag groups or validation, reject invalid playlist bounds, and return concise errors for input, filesystem, EOF, and interrupt failures.
- [x] Implement core.validate_options and remove mkdir from build_command. Respect configured audio defaults, preserve both manual and automatic subtitle requests, and use safe shell quoting for displayed commands. Verify locally installed yt-dlp help for force-redownload and container flags before correcting those semantics; add regression assertions for each verified change.
- [x] Move destination creation to actual execution, catch spawn errors, and map interrupts to cancellation. Do not persist dry-run entries or log credentials. Repair --save-as-default output destination handling and batch-history consistency. Validate --print-url semantics in Task 3.
- [x] Run both test modules; verify all pass. Run help and representative dry-run commands with temporary XDG paths to confirm no real user state is changed.

### Task 3: Managed download and search jobs

**Interfaces:** jobs.JobEvent(kind: str, data: dict); jobs.ManagedJob(cmd: list[str], search: bool = False); start() -> None, poll() -> list[JobEvent], cancel() -> None, close() -> None; finished: bool. jobs.parse_progress(line: str) -> dict | None. jobs.search_command(query: str, limit: int) -> list[str]; jobs.parse_search(output: str) -> list[dict] with title/url entries.

- [x] Add tests/test_jobs.py using fake child scripts: incremental output arrives before exit; final event follows exit; missing executable produces an error; huge output stays bounded; progress parsing tolerates missing ETA; cancellation before launch and after progress reaps children; malformed and failed partial search output does not become a successful result.
- [x] Run `python3 -m unittest discover -s tests -p test_jobs.py -v`; confirm failures from absent interfaces.
- [x] Implement fetchit/jobs.py with a worker thread, bounded event queue, bounded diagnostic tail, subprocess pipes, and process groups on POSIX. Use a stable progress template supported by installed yt-dlp. Treat 100% media download as progress until postprocessing and successful process exit finish the job. Make cancellation/startup synchronized and escalate termination after a bounded grace period.
- [x] Implement structured search via yt-dlp JSON output and bounded result counts. Accept only usable entry dictionaries and safe source URLs. Propagate stderr and exit status. Use shared structured search helpers for cli.do_search and ui.flow_search; --print-url emits URLs, and dry-run never searches the network.
- [x] Repair prompt EOF/interrupt handling, selected-default behavior, and batch target history in fetchit/ui.py with regressions in tests/test_cli.py.
- [x] Run jobs and CLI tests; confirm worker threads and processes have exited after tests.

### Task 4: Terminal-independent forms and navigation

**Interfaces:** tui_state.Field(key: str, label: str, value: str, choices: tuple[str, ...] = ()); tui_state.AppState(cfg: dict, dry_run: bool = False); fields: list[Field], screen: str, focus: int, status: str; navigate(key: str) -> str | None returns action identifiers; download_args() -> SimpleNamespace; settings_values() -> dict. tui_state.safe_text(value: str) -> str removes terminal controls while retaining printable Unicode.

- [x] Add tests/test_tui_state.py: Tab/Shift-Tab cycle focus, arrows change choices, q edits text fields but quits navigation, Escape returns to navigation, editing/backspace preserves pasted URL content, defaults initialize fields, validation retains input on failure, and pasted Unicode/control characters are handled safely.
- [x] Run `python3 -m unittest discover -s tests -p test_tui_state.py -v`; confirm missing-interface failures.
- [x] Implement fetchit/tui_state.py with screen-specific form definitions for Video, Audio, Playlist, Search, Batch, and Settings. Reuse core.validate_options and config validation; settings edits reject invalid values rather than silently resetting them. Include audio batch mode, subtitle/sponsor toggles, and all specified settings. Keep active-job and history/search selection state separate from editable forms.
- [x] Add history-clear confirmation and search-result selection assertions; run the module and confirm all pass.

### Task 5: Full-screen curses application and dispatch

**Interfaces:** tui.run(cfg: dict, dry_run: bool = False) -> int uses curses.wrapper; tui.draw(stdscr, state: AppState) -> None clamps output; tui.available() -> bool checks curses and terminal support. CLI selects this interface for a terminal session without targets; prompt fallback remains available when unsupported.

- [x] Add tests/test_tui.py using a fake curses window: clipped drawing at narrow/tiny dimensions cannot exceed bounds; resizing preserves AppState fields; completion versus cancellation produces distinct status; missing tools appear as useful messages; clearing history requires confirmation; no-target piped input prints help without entering curses.
- [x] Run `python3 -m unittest discover -s tests -p test_tui.py -v`; confirm failures before implementation.
- [x] Implement fetchit/tui.py: charcoal/cyan panels, header/sidebar/footer, compact navigation at narrow widths, resize notice below minimum dimensions, bounded sanitized logs, progress/speed/ETA, editable forms, history scrolling, search selection, settings save, and in-app error reporting. Drain ManagedJob events in the main loop; retain input across job failures.
- [x] Implement safe cancellation/exit cleanup in try/finally and curses.wrapper. Detect unsupported terminals before initialization; use prompt fallback where appropriate and avoid switching to prompts after arbitrary internal errors. Wire cli.main to dispatch without importing curses for direct commands.
- [x] Run the entire suite with `python3 -m unittest discover -s tests -v`; verify passes. Exercise a pseudo-terminal with fake yt-dlp for navigation, text editing, resize, download progress, cancellation, and terminal restoration. Inspect a screen capture or faithful rendered terminal frame if available.

### Task 6: Final audit and user documentation

**Interfaces:** Existing entry points ./fetchit-cli and python3 -m fetchit remain usable.

- [x] Audit the spec against implemented screens, CLI behavior, history statuses, fallback, validation, persistence, and process cleanup. Reproduce any newly found defect first and add its regression before fixing it.
- [x] Update README.md with launch instructions, dependency availability/platform notes, actual shortcuts, a layout example, direct CLI examples, and dry-run/fallback behavior.
- [x] Run `python3 -m unittest discover -s tests -v` and `python3 -m compileall -q fetchit tests`; expected exit status zero. Run help/version and temporary-directory video/audio/playlist/batch dry-run smoke checks; confirm zero new output directories and no changes to actual config/history.
- [x] Review the full change for secret-bearing logs, accidental dependency additions, unfinished placeholders, and unbounded threads/output. Obtain an independent review if authorized by the selected execution workflow.
- [x] Deliver links to relevant files, exact verification outcomes, and any live-network or platform behavior not tested. Git commits are unavailable in the current folder; leave reviewable source changes without modifying repository metadata.

## Execution recommendation

Implement natively in this chat. The six tasks share option and job interfaces, and one implementer can keep them consistent with lower coordination cost. Delegate only if the user selects subagent-driven execution or the chosen execution skill explicitly requires a reviewer.

## Self-review

All spec sections map to Tasks 1–6. Shared signatures match between tasks; each Review Focus condition has an owning test. The plan keeps public entry points and avoids dependency installation. Subprocess, fallback, persistence, and rendering tests use temporary state and fake processes; live-provider verification remains a disclosed limitation if not performed.
