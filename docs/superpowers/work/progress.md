# SDD ledger — plan: docs/superpowers/plans/2026-10-14-terminal-app.md
Ruling: Work directly in the supplied folder; no usable Git repository exists — approved spec forbids creating/replacing metadata — no branch isolation or commits are available.
Ruling: Keep the ledger in docs/superpowers/work instead of Git-based workflow scripts — scripts require repository metadata absent here — progress remains reviewable, without commit ranges.
Pre-flight: Tasks 1/2 share config validation; signatures agree.
Pre-flight: Tasks 2/3/4 share normalized command options; signatures agree.
Pre-flight: Tasks 3/5 share managed events; signatures agree.
Pre-flight: Tasks 4/5 share AppState; signatures agree.
Design tokens: charcoal #161b22, panels #21262d, cyan #79d8ef, text #e6edf3, muted #9da7b3, green #86d39a. Terminal monospace; left alignment; generous two-line field spacing; live transfer rail is the visual focus.
Task 1: complete — 6 persistence tests pass; reproduced 4 failures and 1 malformed-row exception before fixes.
Task 2: complete — all 21 tests pass. Installed yt-dlp help confirms force-overwrites and remux-video semantics. No network test required: original flag parser swallowed dry-run, exposing the defect during initial reproduction.
Task 3: complete — 34 tests pass including 8 real subprocess tests. Search uses JSON and rejects partial failed output. Prompt defaults and batch history repaired.
Ruling: Dry runs do not persist history in any mode — audit showed simulation writes real user state — UI still labels the on-screen outcome as dry run.
Task 4: complete — 10 navigation/form tests pass. Form input survives screen switching, settings reject invalid edits, and search selection prefills a download.
Task 5: complete — 50 unit/regression tests plus real pseudo-terminal navigation/editing/resize/cancellation/restoration pass.
Ruling: Small terminals show a resize screen inside curses rather than abandon to prompt mode — preserves entered drafts as the spec's resize section requires — users must resize or quit.
Final review: independent read-only reviewer found six Important issues and no Critical/Minor issues; 51 pre-review tests passed.
Final: fixed lingering cancellation child — test_cancel_kills_child_even_when_parent_exits_and_pipe_closes RED→GREEN; suite 60/60.
Final: fixed malformed search completion — test_malformed_search_url_still_emits_completion RED→GREEN; suite 60/60.
Final: fixed equals-form credential disclosure — test_equals_form_credentials_are_redacted RED→GREEN; suite 60/60.
Final: fixed prompt low-resolution defaults — test_prompt_video_accepts_low_resolution_defaults RED→GREEN; suite 60/60.
Final: fixed corrupt history encoding — test_invalid_history_encoding_is_tolerated RED→GREEN; suite 60/60.
Final: fixed minimum-size field/action overlap — test_minimum_size_reserves_separate_field_and_action_rows RED→GREEN; suite 60/60.
Final: fixed additional audited terminal fallback, explicit playlist forwarding, and cancellation history status — three corresponding regression tests RED→GREEN; suite 60/60.
Final: Ruling: Live downloads/provider/auth/real ffmpeg conversion remain unverified — deterministic fake jobs validate local behavior without relying on external services — provider failures or codec incompatibilities may remain.
Final: Ruling: macOS and non-POSIX behavior remain unverified — only Linux is available; non-POSIX uses direct CLI/prompt fallback — platform-specific differences may remain.
Final: Ruling: Preview image reviewed by author rather than independent reviewer — PNG is rendered from actual draw() output and visually inspected — aesthetic judgments remain subjective.
Task 6: complete — documentation and preview saved; 9 CLI smoke checks passed with no directories or persisted state created; compileall succeeded; final regression suite 60/60.
2026-10-15 follow-up: reproduced user URL with yt-dlp simulation outside network sandbox. YouTube returned HTTP 429 followed by Sign in to confirm you are not a bot. No media downloaded and no browser cookies accessed.
Fixed error display: select the actual error instead of concatenating extractor chatter into a clipped status; show concise authentication/rate-limit guidance and retain individual diagnostic lines. Preserve unterminated final error lines in worker completion. Three new regressions verified RED→GREEN; full suite 63/63 and compileall pass.
2026-10-15 browser diagnosis: explicit user-authorized no-download check could unlock Helium's existing session using the existing native keyring; no keys/cookies exported or printed. User then requested a browser-independent architecture; stopped Helium integration before implementing it and removed its temporary test scaffold.
Anonymous recovery: exact public video succeeded without cookies via web_embedded,tv_downgraded. Added one automatic fallback after known YouTube bot/429 extraction failure, respecting explicit authentication/player options and suppressing retries after media starts. GUI and CLI share process cleanup and one completion.
Live Fetchit check: --simulate --check-formats --no-cookies --no-cookies-from-browser; default blocked, alternative checked 134+140, exit 0. No media/history saved.
Focused independent review found direct stdout truncation after shared execution refactor. Regression tests for long JSON and 1.28MB binary output failed then passed with separate raw stdout/stderr relays; preview/recovery notices use stderr for real runs. Full suite 70/70; compileall passes.
