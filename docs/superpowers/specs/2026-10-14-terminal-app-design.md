# Fetchit terminal app design

## Intent and success criteria

Turn the existing video downloader into a polished, keyboard-driven terminal application inspired by OpenCode. Keep the downloader usable through existing command-line invocations and retain its standard-library-only Python setup with system yt-dlp and ffmpeg. Audit the project, fix reproducible defects, and document remaining verification limits rather than claim every possible bug is eliminated.

Success means users can configure and run a download, observe its progress, cancel it, inspect history, and edit defaults without leaving the full-screen interface. Invalid input, corrupt local state, missing executables, terminal resizing, and download failures must produce useful messages rather than tracebacks.

## Chosen approach

Use Python curses for the full-screen application. It requires no new Python dependency and supports keyboard input, panels, and terminal resizing. A small terminal or unavailable curses should receive a readable fallback to the existing prompt interface. Noninteractive CLI commands continue to work without curses initialization. If no target is supplied and standard input is not a terminal, show help rather than enter a prompt loop.

Alternatives considered: Textual would simplify richer widgets but add package installation; an ANSI numbered menu would retain the present limitations. The curses implementation is the approved direction.

## Visual design and navigation

Use a charcoal terminal background where supported, cyan accents, muted secondary text, and distinct success, warning, and failure colors. Avoid reliance on emoji character widths. The header shows Fetchit and the current screen. A left sidebar lists Video, Audio, Playlist, Search, Batch, History, and Settings. The main panel holds the selected form or results. A bottom status line explains available shortcuts and reports dependency readiness.

Tab and Shift-Tab move focus; arrows move among navigation items or choices; Enter activates the focused item; Escape backs out or returns to navigation; q quits from navigation. Text fields accept ordinary editing and pasted text. Quit shortcuts must not interfere with entering URLs or search queries. During an active download, cancellation is explicit and shutdown waits for process cleanup. The terminal is restored on every exit path.

At narrow sizes, collapse the sidebar into a compact navigation strip. Below a practical minimum size, show a resize message without raising drawing errors. Clamp all drawing to the current terminal dimensions and remove control characters from external titles and output.

## Screens and flows

### Downloads

Video: URL, quality, container, subtitle language and subtitle toggle, sponsor removal toggle, and destination. Audio: URL, audio format, quality, and destination. Playlist: URL, optional item range, quality, container, and destination. Batch: file path, mode, quality or audio format, and destination.

Initialize fields from validated saved defaults. Validate fields before launching; retain entered values after failure or cancellation. Show the selected target and effective options alongside progress. Do not introduce parallel download scheduling in this version: run one yt-dlp command at a time, including its playlist or multi-target behavior.

### Search

Search a query with a bounded result count. Fetch structured JSON entries from yt-dlp rather than title/ID line pairing. Display title and source URL, allow selection, and launch the selected result through the download form. Show subprocess failures and cancellation separately from empty results. Search must not freeze navigation or screen refresh.

### History

Show recent target, status, and timestamp in a scrollable list. Distinguish success, failure, cancellation, and dry run. Clearing history requires an in-app confirmation. Record batch jobs consistently across prompt and full-screen modes. A shared multi-target command's result describes the command outcome, not independently verified success for every target.

### Settings

Edit destination, default video quality/container, audio format/quality, subtitle language, retries, fragment concurrency, and metadata/thumbnail defaults. Validate before saving. Save atomically and show filesystem errors in the UI. Unknown config keys can remain preserved, but recognized invalid values fall back to safe defaults on loading.

## Architecture and data flow

Keep argparse and direct command dispatch in cli.py, yt-dlp command construction and execution in core.py, persistence in config.py/history.py, and the existing prompt fallback in ui.py. Add a focused curses application module and, if needed, a separate process/progress helper rather than making ui.py monolithic.

CLI dispatch chooses the full-screen interface only for a terminal session without a download target. The full-screen forms produce the same normalized download options used by the CLI. Command construction validates options and has no filesystem writes. Directory creation occurs only when an actual download starts.

A managed subprocess executes yt-dlp without a shell and streams bounded output through a worker/queue to the UI loop. Only the UI thread draws. Progress extraction uses explicitly configured yt-dlp output where practical; ordinary diagnostic lines remain visible when progress is unavailable. Output buffering is bounded. Completion follows the subprocess exit status, including postprocessing, rather than a reported 100% download figure. Cancellation stops and reaps the subprocess and its child processes on supported POSIX platforms, with a safe platform fallback.

## Bug audit and corrective scope

Confirmed with local reproductions:

1. argparse.REMAINDER absorbs options after a positional URL, so quality flags are silently ignored. Remove redundant remainder parsing while preserving explicit passthrough after bare -- and verify mixed positional/option ordering.
2. build_command creates output directories during dry runs. Make construction side-effect-free.
3. Valid JSON history containing non-object rows crashes display. Filter or validate records and handle invalid display limits.
4. Invalid config values such as a null destination propagate into command construction and crash it. Validate recognized config fields and effective command options.

Also investigate and fix where verified: search --print-url output, subprocess error handling, EOF and interrupt handling inside prompt flows, batch history, default values ignored by forms, invalid numeric arguments, contradictory options, force-redownload semantics, container guarantees, subtitles with manual and automatic captions, and filesystem errors. Preserve passthrough behavior and existing documented commands. Do not log secret-bearing command arguments such as proxy credentials or user-agent values unnecessarily.

Behavior changes must be supported by a failing regression test or a clear reproduction before the fix. No unrelated feature expansion, system configuration changes, or automatic dependency installation.

## Validation

Use standard-library unittest with temporary config/data directories and fake or mocked yt-dlp processes. Cover argument ordering and passthrough, option validation, side-effect-free dry runs, corrupt state, persistence errors, search parsing, progress parsing, cancellation, and terminal-independent navigation state. Run the entire suite after fixes.

Exercise CLI help, representative video/audio/playlist/batch dry runs, config/history commands, and piped input behavior. Use a pseudo-terminal to verify startup, navigation, editing, resizing, cancellation, and clean exit/terminal restoration. Inspect a rendered full-screen capture where the environment permits it. Check installed yt-dlp documentation for the subprocess flags actually used. Real network downloads are optional verification and any untested live-provider behavior must be disclosed.

## Delivery

Update README with launch instructions, keyboard shortcuts, screenshots or a layout example if practical, fallback behavior, dependency requirements, and accurate command examples. Deliver source changes, regression tests, verification results, and any remaining limitations in the existing folder. This directory currently has no usable Git repository, so committing is unavailable unless repository metadata is supplied; do not initialize or replace Git metadata as part of this UI work.
