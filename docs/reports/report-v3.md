# E.V.E. test report, third pass (v3)
Date: Mon 19 Oct 2026 (Asia/Manila, UTC+8). Repo: JoeSecondBrainVault/EvE, local clone /workspace/EvE. Nothing was pushed and the remote was not changed.

## Summary

**New commits:** 1, fast-forwarded cleanly from `8e0dd4f`; nothing local was discarded.
- `3eda65c`, **2026-10-19 6:05:10 PM UTC+8**, Joebelle-01 <dumapias.joebelle16@gmail.com>.
- Message: "fix(security): remediate report-v2 vulnerabilities (S1-S4) and functional defects (N5-N17, #3, #4, #13, #28)".
- 31 files changed, +566 / −191. Dependencies did not change. Notable: `dashboard/app/api/token/route.ts` was **deleted**; `main.py`, `security.py`, `mcp/*`, `lib/api.ts`, `tools/page.tsx`, `Navbar.tsx` and `settings/page.tsx` were reworked.
- This commit is a direct response to report-v2: it set out to fix S1–S4, N5–N17, and old bugs #3, #4, #13 and #28.

**Fixed vs still open (the v2 open items):**
- **Closed (verified by reproduction):** S1, S3, S4, N5/#3, N6 (core), N7 (backend), N8, N9, N10, N11, N12/#9, N13, N14, N15/#13, N16, N17, #28 (RTX text), plus a real logout.
- **Still open / only partial:**
  - **S2/#4 — still a HIGH remote-code-execution hole (only partly fixed).** The new arg filter blocks a *separate* `-c` arg, but I executed arbitrary code five different ways that all slipped through (details below).
  - **N6 residual (Low/Medium):** voice, tray and CLI session starts still hard-code `consent_confirmed=True`, so those paths still record without a consent confirmation. The default and the API/UI paths are now gated.
  - **N7 residual (Low):** the backend now requests Gmail and `calendar.events.readonly`, but there is still no Gmail "Connect" card in the UI, and the per-app connect endpoint rejects `app=gmail` (pattern allows only classroom/calendar/docs/drive/meet). So the two Gmail/Calendar MCP tools remain unreachable through the normal UI.
  - **#28 residual (Low):** Settings still shows "Local Offline (Ollama 7B)" as a hardcoded label.
  - **#35 (Low):** npm audit still reports 5 high (Tailwind 3 / fast-glob), build-time only.
  - **New N18 (Low/Medium):** saving an MCP server **persists the entry to disk before** connecting, so a bad/hostile entry (and any code it runs) is written to `mcp_servers.json` even when the API returns `status: error`, and an `enabled` one would be re-launched on restart.

**New bugs this pass:** N18 (MCP entry persisted before connect) and N19 (default vault path hardcoded to the developer's PC). No other new functional regressions were found in the diff.

**Security:**
- **Fixed and verified:**
  - **S1 (token disclosure):** `GET http://127.0.0.1:8765/` now redirects to `http://localhost:3001` with **no token**. The dashboard `/api/token` route was deleted (now 404).
  - **S3 (token in URLs):** `?token=` is now accepted **only** on streaming-audio routes. `GET /api/status?token=` and `/api/sessions?token=` return 401; `/api/sessions/1/audio/them?token=<valid>` returns 200, and a wrong token there returns 401. The launcher, tray and run.ps1 no longer put the token in URLs.
  - **S4 (URL token overwrite):** a `?token=` in a dashboard URL no longer overwrites an existing stored token, and the parameter is stripped from the address bar immediately (both confirmed with Playwright).
  - OAuth: single-use state is enforced (`/exchange` pops the pending entry; a second exchange fails with "expired state"), N11 closed.
- **Still open — HIGH: MCP arbitrary command execution (S2/#4).** The allowlist restricts the command to python/node/uv (or the venv), and it blocks shell metacharacters and a list of inline-eval flags, but the flag check is an **exact-string match on each arg**. I confirmed arbitrary code ran (each wrote a marker file) via:
  1. a **glued** flag: `args:["-c__import__('pathlib')…write_text(...)"]` (python accepts `-cCODE`);
  2. **combined short flags**: `args:["-Ic", "<code>"]`;
  3. an **arbitrary .py script path**: `args:["/tmp/eve_v3_script.py"]`;
  4. the **venv python absolute path** plus a glued `-c`;
  5. **`node -p`** (`-p`/`--print` is not in the blocklist), `args:["-p","require('fs').writeFileSync(...)"]`.

  Because the entry is written to disk before the connect attempt (N18), the payload runs even though the response says "Failed to connect". This remains a full local-RCE for anything that can reach the API (which, with the token now protected, means local processes that can read `data/api_token`). **Recommended fix:** don't filter flags; instead pin each server to a fixed, app-shipped command+args (name → preset), or require the `-m eve.mcp.servers.*` form and reject *all* other args/scripts.

**Buttons (Playwright crawl, 101 controls across 9 pages):** every button has a working handler; no dead/placeholder buttons and no TODOs.
- Real + working: all app-launch tiles (200), Mark Done, Copilot, Ask Eve, STOP & ANALYZE, lecture tabs/play/seek, Tasks confirm/start/done, Sync Google (401 with a clear message when not connected), Assignments analyze, chat send, Settings Save Token/Refresh/Purge/Simulate, Tools refresh, **the new MCP Hub (enable, disable, and 3 Test Call buttons all hit the API)**.
- UI-only by design: Live All/Instructor/You filters, Copilot collapse icon (still no aria-label), lecture tabs, Assignments/Overview mode toggles, Settings eye toggles, chat suggestion chips.
- Placeholder-ish: Live "Add timestamp bookmark" is still client-only (lost on reload, never saved).
- Broken only due to the Linux box: Overview/Tools "Join Meet" → 500 "Google Chrome executable not found" (now a proper JSON 500 **with** CORS, so the UI shows the real message, not "Failed to fetch"); Open vault needs Windows `cmd`; app tiles are Windows-only.
- Google buttons stay correctly disabled until a client secret is loaded.

**Login:**
- Missing token: no silent auto-login anymore (the `/api/token` fallback is gone). The dashboard shows an "Invalid API Token" banner and an "Auth Error (401)" footer, with a link to Settings.
- Wrong token: same banner/footer; 401 on every `/api/*` route.
- Valid token: works; persists across reloads.
- Logout: a real "Log Out" button now exists in Settings; it clears the stored token and the app stays logged out (banner shown, no silent re-login).
- Protected endpoints: all `/api/*` reject missing/wrong tokens; `/`, `/health` and the state-checked Google callback are the only open routes, and `/` no longer leaks the token.

**MCP:**
- One server: `google_workspace` (`eve.mcp.servers.workspace`), 3 read-only tools: `get_classroom_assignments`, `get_calendar_events`, `list_unread_emails`.
- Shipped default is now `command: <sys.executable>`, disabled (N9 fixed) — it connects on Linux now.
- Enabled through the **restored Tools → MCP Hub UI**: it connected, listed all 3 tools, and each "Test Call" returned 200.
- Each tool invoked with safe inputs (no real credentials) returns "Google account not logged in" with **`isError: true`** (N10 fixed). Unknown tool → "not found", isError true.
- Raw JSON-RPC: `initialize`/`tools/list` correct; unknown method → -32601; **malformed JSON now → -32700** (fixed).
- Not tested against real data: Google login is required; the Gmail/Calendar tools also can't be reached via the UI yet (N7 residual).

**Tests / lint / build:**
- pytest: **67 passed** (one flake was caused only by my mock-Ollama harness returning unnormalized embeddings; with the real embedding path it passes).
- ruff `--select F`: **all checks pass** (the F821 `JSONResponse` and F811 from v2 are gone). `--select F,B`: 14 B008 remain (standard FastAPI `Depends/File/Form` defaults, harmless).
- bandit `-ll`: clean. pip-audit: no known vulnerabilities. tsc `--noEmit`: clean. `npm run build`: OK, 10 routes (the `/api/token` route is gone). npm audit: 5 high (build-time).

---

## Recheck of every v2 open item
| v2 item | v3 status | Evidence |
|---|---|---|
|**S1** unauth token disclosure|**Fixed**|`GET /` → `Location: http://localhost:3001` (no token); dashboard `/api/token` → 404; route file deleted|
|**S2 / #4** MCP command exec|**Still HIGH (partial)**|Glued `-c…`, `-Ic`, `.py` script path, venv-python+`-c`, and `node -p` all executed code (marker files written). Separate `-c`/`-e`/`bash`/`;`/non-venv path are now blocked|
|**S3** token in URLs|**Fixed**|`?token=` honored only on `/api/sessions/*/audio/*`; 401 elsewhere; removed from launcher/tray/run.ps1|
|**S4** `?token=` overwrites stored token|**Fixed**|Existing token kept; `?token=` stripped from URL bar (Playwright)|
|**N5 / #3** global handler crash → "Failed to fetch"|**Fixed**|`JSONResponse` imported; a 500 now returns JSON **with** `access-control-allow-origin`; ruff F clean|
|**N6** consent bypass|**Fixed (core); residual**|`SessionManager.start` default is now False and raises without consent; Meet API gated on `consent_confirmed`; UI has consent checkboxes. **Residual:** voice/tray/CLI still pass `consent_confirmed=True`|
|**N7** Gmail/Calendar MCP scopes|**Backend fixed; UI residual**|`gmail.readonly` + `calendar.events.readonly` now in scopes. **Residual:** no Gmail connect card; `/connect` rejects `app=gmail`|
|**N8** MCP UI removed|**Fixed**|Tools page has a "Model Context Protocol (MCP) Hub" with server list, enable/disable and per-tool Test Call|
|**N9** default `command: "python"`|**Fixed**|Default config uses `sys.executable`; connects on Linux|
|**N10** wrong isError flag|**Fixed**|Auth-error tool responses return `isError: true`|
|**N11** OAuth exchange replay|**Fixed**|Pending entry is popped; second exchange → "expired state". `state` added to the exchange body|
|**N12 / #9** reprocess wipes task status|**Fixed**|Marked task 'done', reprocessed session 3 → task kept **done** (title-based upsert)|
|**N13** reserved/colliding note names|**Fixed**|`safe_filename("CON")` → `Note-CON`; same-day different-session note gets a "(Session N)" suffix|
|**N14** silent .exe upload|**Fixed**|Shows "Unsupported file format 'evil.exe'. Please select a .pdf, .docx, .txt, or .md file."|
|**N15 / #13** no 401 banner|**Fixed**|"Invalid API Token" banner + "Auth Error (401)" footer + Settings link|
|**N16** Meet open with no feedback|**Fixed**|Falls back to `window.open` and shows a clickable "Join class on Google Meet" link when the browser didn't open|
|**N17** quiz unknown course|**Fixed**|`quiz_me("Biology")` → "No quiz items found for course 'Biology'…" (no silent fallback)|
|**#28** hardcoded "RTX 4060"|**Fixed; residual**|"RTX 4060" gone; device now resolved dynamically. **Residual:** "Local Offline (Ollama 7B)" label still hardcoded|
|**#35** tsbuildinfo / npm audit / lint|**Partial**|5 high npm audit findings remain (build-time); `lint` is still `tsc`|
|**Logout** (was missing)|**Fixed**|Real Log Out button in Settings|

## New bugs this pass
| ID | Severity | Bug | Evidence |
|---|---|---|---|
|N18|Low/Medium|`save_server` writes the server entry to `mcp_servers.json` **before** attempting the stdio connect, so a rejected/hostile entry (and the code it runs via S2) is persisted even though the API returns `status: error`; an `enabled` one is re-spawned on the next startup|`mcp/manager.py save_server`; confirmed 6 junk entries persisted during the S2 test (cleaned up afterward)|
|N19|Low|`config.py` defaults `vault_path` to `C:\Users\Legion\Documents\Obsidian Vault` (the developer's own PC). On another Windows user it points at a non-existent or unwritable folder; on Linux/macOS it becomes a relative folder created in the working directory|`backend/eve/config.py:85`; reproduced (stray folder created in repo root, then deleted)|


## Controls, page by page (Playwright, 101 controls)
Key: Real = calls backend and works; UI = client-only by design; Placeholder = looks functional but doesn't persist; Broken(env) = fails only because the box is Linux.

| Page | Control | Result |
|---|---|---|
|Overview|App tiles ×6|Real `POST /api/integrations/apps/launch` → 200 (Windows-only effect)|
||Mark Done ×N|Real `POST /api/tasks/{id}/status`|
||Join Meet & Auto-Record|Broken(env): 500 "Chrome not found" — now proper JSON+CORS, real message shown|
||Manual Rec / Google Meet tabs, consent checkbox (pre-checked), links|UI / navigation|
||"MCP Tools Hub →"|Now leads to the real MCP Hub (N8 fixed)|
|Live|All/Instructor/You|UI filter|
||Add timestamp bookmark|Placeholder (client-only, lost on reload)|
||Copilot Talking Points|Real `/api/copilot/suggest`|
||Ask Eve (submit)|Real `/api/voice/interact`|
||Collapse icon|UI, no aria-label|
|Lectures|Search / course select|UI filter|
|Lecture/1|Tabs, Play, seek, Speaker|Real audio / UI|
||Mic|Real; 404 when no `me.wav` (no message)|
|Tasks|Sync Google|Real; 401 "Google account not authenticated" (correct)|
||Confirm / Start / Mark done|Real|
|Assignments|Upload / Paste toggles|UI|
||.exe upload|Rejected with a clear message (N14 fixed)|
||Analyze Coursework|Real `/api/assignments/analyze` (disabled while empty)|
|Tools|Refresh connection status|Real `GET /google/apps`|
||Choose client_secret.json / Save|Real (tested with a fake client); then Connect enables|
||Connect ×5, Sync, Create Meet, Show docs/files, Push deadlines|Disabled until a client secret is saved (correct gating); not invoked (need Google login / are external writes)|
||Join class & record (consent pre-checked)|Real; URL validation; launch Broken(env)|
||Open vault|Real; Broken(env) on Linux (`cmd` missing)|
||**MCP Hub: Refresh / Enable / Disable Server**|Real `GET`/`POST /api/mcp/servers`|
||**MCP Hub: Test Call ×3**|Real `POST /api/mcp/call` → 200|
|Chat|Suggestion chips|UI (fill input)|
||Send|Real `/api/chat`; cited answer|
|Settings|Save Token|Real; verifies ("Token verified and saved")|
||**Log Out**|Real; clears token, stays logged out|
||Save & Activate API Keys|Real; disabled while empty|
||Sign in with Google|Disabled until configured|
||Simulate "Hey Eve" / Refresh Devices / Purge Expired Audio|Real|

## Login and auth details
- Missing token: banner + footer + Settings link; no auto-login (the `/api/token` fallback was removed).
- Wrong token: same; 401 on all `/api/*`.
- Valid token: works, persists across reloads.
- Logout: clears the stored token; app stays logged out (no silent re-login).
- Open routes: `/` (no longer leaks token), `/health`, Google callback (state-checked). Everything else requires the bearer token; `?token=` is only honored on audio routes.

## MCP details
| Server | Tool | Added via | Listed | Invocation (safe input) | Status |
|---|---|---|---|---|---|
|google_workspace|—|Shipped default (`sys.executable`, disabled)|—|Connects on Linux now (N9 fixed)|OK|
|same|get_classroom_assignments(course_name="IT 222")|Tools → MCP Hub "Enable" (UI) and API|Yes|"Google account not logged in", `isError: true`|Untested vs real data (needs Google login)|
||get_calendar_events(max_results=3)|same|Yes|same|Untested (credentials); also not reachable via UI (N7)|
||list_unread_emails(max_results=3)|same|Yes|same|Untested (credentials); Gmail connect not in UI (N7)|
||nonexistent_tool|—|—|"not found", isError true|OK|

Raw JSON-RPC: initialize/tools-list correct; unknown method → -32601; malformed JSON → -32700 (fixed). Only commands shipped by the repo were run; no external writes; `data/mcp_servers.json` restored to the shipped default afterward.

## Tool results
- pytest: 67 passed (the 1 flake was my mock-Ollama harness; real path passes).
- ruff `--select F`: clean. `--select F,B`: 14 B008 (FastAPI default args, benign).
- bandit `-ll`: clean. pip-audit: no known vulnerabilities.
- tsc `--noEmit`: clean. `npm run build`: OK (10 routes). npm audit: 5 high (build-time; Tailwind 3 / fast-glob).

## Recommended fixes (priority)
1. **S2/#4 (HIGH):** stop filtering interpreter flags. Pin each MCP server to a fixed app-shipped command+args, or require exactly `["-m","eve.mcp.servers.<name>"]` with the venv python and reject every other arg or script path. Also validate **before** writing to disk (N18).
2. N6 residual: have voice/tray/CLI honor a real consent flag instead of hardcoding True.
3. N7 residual: add a Gmail connect card and allow `app=gmail` in `/connect`, or drop the Gmail/Calendar tools.
4. Minor: remove the hardcoded "Ollama 7B" label; add an aria-label to the Live collapse icon; persist Live bookmarks; Tailwind 4 to clear npm audit.

## Box state
- Running: backend (fake audio) 127.0.0.1:8765 (vault pointed at /workspace/EvE-run/vault), mock Ollama :11434, dashboard :3001 (new build).
- Repo: fast-forwarded to `3eda65c`; `git status` clean. A stray `C:\Users\Legion\Documents\Obsidian Vault/` folder was created in the repo root by one backend restart I did without the vault override (see N19); I deleted it and restarted with `EVE_VAULT_PATH` set.
- Test cleanup done: fake client_secret deleted, test MCP junk entries removed, `mcp_servers.json` reset to shipped default, `/tmp/eve_v3_*` and probe scripts deleted, backend restarted to drop the in-memory MCP client, empty `.env` removed.
- Screenshots: `/workspace/EvE-report/screenshots-v3/` (auth_*, overview_meet_error, tools_mcp_hub, assignments_exe_warning, settings, plus the full crawl set).
