# E.V.E. test report, second pass (v2)
Date: Mon 19 Oct 2026 (Asia/Manila, UTC+8). Repo: JoeSecondBrainVault/EvE, local clone /workspace/EvE. Nothing was pushed and the remote was not changed.

## Summary

**New commits:** 1. The local branch was fast-forwarded from `cdf688c`, and nothing local was discarded.
- `8e0dd4f`, 2026-10-19 4:47 PM UTC+8, Joebelle-01. "feat: real Google classroom OAuth integration, desktop launcher fix, and clean UI".
- 34 files changed, +1556 / −775. The main areas:
  - backend `main.py` (+342), `integrations/google.py`, `security.py`, `config.py`, `session.py`, `voice/assistant.py`
  - the rewritten dashboard `tools` page
  - the new `dashboard/app/api/token/route.ts`
  - `lib/api.ts`, `app.py`, `tray.py`, `run.ps1`
- Dependencies did not change (pyproject and package-lock are the same).

**Fixed vs remaining (35 v1 bugs):** **26 fixed, 3 fixed with side effects (#5, #6, #9), 4 partly fixed, 2 still present.**
- Still present:
  - **#3:** unhandled errors still show as "Failed to fetch". The new global handler crashes because `JSONResponse` is never imported.
  - **#4:** the MCP API can still run any command, now through an allowlisted interpreter: `python3 -c …`. I proved this by creating `/tmp/eve_pwned` (then deleted it).
- Partly fixed:
  - **#13:** a wrong token still gives silent zeros with no banner.
  - **#21:** the dev-port mismatch is mostly fixed.
  - **#28:** Settings still says "RTX 4060" and "Ollama 7B".
  - **#35:** there are still 5 high npm audit findings, and `npm run lint` is now just `tsc`.
- Fixed with side effects:
  - **#9:** reprocessing no longer duplicates rows, but it now wipes task statuses you changed by hand.
  - **#5/#6:** voice, tray and Meet starts now work, but recording consent is auto-confirmed.

**New bugs:** 17 (S1–S4 security, N5–N17). Details are in the "New bugs" section below.

**Security flaws in the new commit:**
- **High:**
  - **Any local process can get the API token with no auth:**
    - `GET http://127.0.0.1:8765/` returns a 307 to `http://localhost:3001?token=<real token>`.
    - `GET http://localhost:3001/api/token` returns `{"token": …}`.

    This defeats the bearer-token model (security.py says the token protects against "other local processes / users"). Neither response has CORS headers, so a web page in a browser cannot read the token.
  - **MCP command execution (#4) still works.**
- **Medium:**
  - The token is accepted as `?token=` on every endpoint and is put in launcher, tray and run.ps1 URLs. That leaks it into browser history and the uvicorn access log (confirmed).
  - A `?token=` in a dashboard URL silently overwrites the stored token (confirmed), so a crafted link breaks or logs out the dashboard.
  - Consent is bypassed: `consent_confirmed` now defaults to True, and voice, tray and Meet hard-code it.
- **Clean:**
  - pip-audit: no known vulnerabilities.
  - bandit `-ll`: clean.
  - detect-secrets: no committed secrets.
  - npm audit: 5 high (braces/micromatch via Tailwind 3; dev/build-time only).
  - OAuth is now correct: `state` + PKCE S256, single-use state in the callback, fixed redirect URI, HTML-escaped error page (XSS test passed).

**Placeholder or UI-only controls:**
- Nothing is a fake button: every button has a handler, and there are no TODOs.
- UI-only or misleading:
  - Overview "Manual Rec" tab.
  - Live: All/Instructor/You filters (by design), Bookmark (client-only, lost on reload, never saved), Copilot collapse icon (no label).
  - Lecture detail: tabs and seek timestamps (by design).
  - Assignments mode toggles.
  - Settings eye toggles.
  - Overview app tiles: Windows-only, no feedback on failure.
  - "Simulate Hey Eve": works, but shows no feedback.
- **The MCP UI was removed:** the Tools page rewrite dropped the MCP section, but the navbar still says "Tools & MCP" and Overview still links to "MCP Tools Hub →".
- Everything Google-related (Connect ×5, Sync, Create Meet, Show docs/files, Push deadlines) stays disabled until a client secret is loaded. That is correct gating.

**Login results:**
- Every `/api/*` route returns 401 with no token and with a wrong token. Open routes: `/` (which leaks the token, see above), `/health`, and the Google callback (state-checked).
- WebSocket `/ws/live`: no or wrong token closes with 4401, an evil Origin gets 403, and the right token gets "hello".
- The token persists across reloads.
- A fresh browser now auto-logs in through `/api/token`.
- A wrong stored token gives silent zeros, the navbar stays on "Connecting…" forever, and the token is never replaced automatically.
- **There is no logout.** Clearing storage just logs you in again silently.
- Settings "Save Token" now checks the token and shows "Invalid token (…401)".

**MCP results:**
- The repo defines one server, `google_workspace` (`eve.mcp.servers.workspace`), with 3 read-only tools: `get_classroom_assignments`, `get_calendar_events` and `list_unread_emails`.
- **As shipped** (`command: "python"`, disabled), enabling it fails on Linux: "No such file or directory: 'python'". On Windows it would use system Python instead of the venv. `POST /api/mcp/servers` still returns `status: ok` when the connect fails.
- **With the venv python** (added through `POST /api/mcp/servers`; there's no UI any more): connected, and all 3 tools are listed.
- Invoking each tool through `/api/mcp/call` with safe inputs always returns "Google account not logged in", but with `isError: false`, which is wrong.
- Raw JSON-RPC checks: `initialize` and `tools/list` are correct, an unknown tool gives `isError: true`, an unknown method gives -32601, and malformed JSON is dropped silently (no -32700).
- **Not tested with real data: Google login is required** (no real credentials were used).
- With the new OAuth scopes, `list_unread_emails` (Gmail is never requested) and `get_calendar_events` (it reads `primary`, but only `calendar.app.created` is requested) **cannot work even after login**.
- The config was restored to the shipped default at the end.

**Tests / lint / build:**
- pytest: **67 passed**. The suite no longer touches the real keyring.
- ruff (F,B): 56 findings, including **F821 `JSONResponse` undefined (main.py:473/480)** and F811 `Session` redefined (assistant.py:287).
- tsc: clean.
- `npm run build`: OK (11 routes).

---

## How it was tested
- Linux box with Python 3.13 venv (openwakeword was installed with `--no-deps` because tflite has no wheel).
- Backend: the real FastAPI app on 127.0.0.1:8765. Stand-ins: the repo's own test fakes (LoopCapture/FakeSTT/EnergyVAD) instead of real audio, and a mock Ollama on :11434 that returns schema-valid JSON. LLM output quality was **not** evaluated.
- Dashboard: `next start` on :3001 with the new build.
- Playwright (headless Chromium) clicked every control on every page. Raw results are in `controls_raw.json`, `crawl1-3.txt` and `targeted_results.json`.
- Windows-only features (Chrome/Meet launch, app tiles, pywebview, tray, keyring) were checked in code or with mocks only.

## Recheck of the 35 v1 bugs
| # | v1 bug | v2 status | How it was verified |
|---|---|---|---|
|1|Stop never generates notes or opens the lecture|**Fixed**|STOP & ANALYZE → confirm → processed → opens `/lectures/5`|
|2|Audio player can't play|**Fixed**|Audio loads with `?token=` (200), readyState 4, plays. The "Mic" source returns 404 with no message when `me.wav` is missing (Low)|
|3|Unhandled errors show "Failed to fetch"|**Still present**|The new `@app.exception_handler(Exception)` raises `NameError: JSONResponse`. `/api/integrations/meet/launch` (Chrome missing) gives a plain 500 with no CORS header, so the UI shows "Failed to fetch" (Overview Meet, Tools Meet dialog)|
|4|MCP API runs any command|**Still present (changed)**|`{"command":"python3","args":["-c","open('/tmp/eve_pwned','w')…"]}` returned 200 and created the file. `/tmp/fake/python` is accepted (basename-only check). `bash` is rejected (400)|
|5|Voice start always fails|**Fixed** (new privacy issue N6)|Voice start returns 200 with a session id|
|6|Meet/tray recording never starts|**Fixed**|With Chrome mocked, Meet launch calls `start(course=None)` correctly. The tray signature matches|
|7|API keys lost after restart|**Fixed**|POST keys → new `Settings()` process sees the key (written as `EVE_*`, `load_dotenv`). The test key was removed afterwards|
|8|Tests delete the real Google login|**Fixed**|keyring is mocked in the tests|
|9|Reprocessing duplicates rows|**Fixed, with a regression**|Processing twice → 2 tasks and 2 flashcards. But a task marked done (id 4) was deleted and recreated as `inbox` (ids 7,8) (N12)|
|10|Failed start leaves a junk lecture|**Fixed**|Capture that raises → 409 "Could not open audio devices", 0 sessions listed, stats 0|
|11|OAuth callback has no `state`|**Fixed**|PKCE S256 + state. Forged state → "Sign-in link expired". The used state can't be replayed. The redirect URI can't be overridden (400). The MCP config uses `sys.executable`|
|12|Google endpoints 500 when unconfigured|**Fixed**|Clear 400/401 messages|
|13|No-token first run looks empty|**Partly fixed**|A fresh browser auto-logs in (through the unauthenticated token endpoint, S1). A wrong token: silent zeros, no banner, navbar stuck on "Connecting…"|
|14|`/lectures/abc` loads forever|**Fixed**|Shows "Lecture not found / Return to Lectures"|
|15|Voice summary KeyError 'title'|**Fixed**|Clean "no notes yet" reply|
|16|Voice quiz problems|**Fixed (minor)**|`course="IT 222"` returns only IT 222 questions, and options are a list. An unknown course (e.g. "Biology") silently falls back to all courses (Low)|
|17|Voice stop returns a whole row|**Fixed**|Returns an int id|
|18|App launcher matches substrings|**Fixed**|Exact `.get()` match|
|19|Meet URL normalizer passes any URL|**Fixed**|`evil.com` and `meet.google.com.evil.com` are rejected|
|20|Misleading "no LLM" message|**Fixed**|Names the providers that are actually configured|
|21|Dashboard port mismatch|**Mostly fixed**|Root and tray probe 3001, then 3000. The OAuth callback no longer redirects (it shows an HTML page). run.ps1 dev mode still uses 3000 and the launcher 3001; that's acceptable now|
|22|Launcher assumes a build exists|**Fixed (code only)**|Builds if `.next` is missing. Not runnable here (pywebview/Windows)|
|23|Unbounded `top_k`|**Fixed**|`le=50` → 422 above that|
|24|Audio lookup matches other sessions|**Fixed**|Session 1's folder removed, session 5 folder `…-5-Lecture-1-intro` present → session 1 audio returns 404 (correct)|
|25|MCP stderr never drained|**Fixed**|A test server writing 300 KB to stderr still connects instantly|
|26|Rate limiter has no lock|**Fixed**|8 threads × 50 calls → exactly 100 allowed|
|27|Empty session shows 0%/100%|**Fixed**|Note shows `0% / 0%`. An empty session still writes a note (Low)|
|28|Hardcoded UI text|**Partly fixed**|"Welcome back, Joe" → "Welcome to E.V.E." Settings still shows "RTX 4060" and the "Ollama 7B" labels|
|29|Chat shows raw Markdown|**Fixed**|Bold citations render (`chat_answer.png`)|
|30|Save Token never verifies|**Fixed**|Wrong token → "Invalid token (Backend returned status 401…)"|
|31|`Low confidence (quote: "...")`|**Fixed**|Not shown for tasks with no evidence|
|32|TS Session.status type wrong|**Fixed**|`stopped/failed/processed` added|
|33|README `--Title`, standalone tray has no callbacks|**Fixed**|README updated; `eve tray` wires start/stop|
|34|Analyze enabled when text is empty|**Fixed**|Disabled until there's text|
|35|tsbuildinfo / npm audit / lint|**Partly fixed**|tsbuildinfo is ignored. **5 high** npm audit findings remain. The `lint` script is now `tsc --noEmit` (no real linter)|

## New bugs (from the new commit)
| ID | Severity | Bug | Evidence / location |
|---|---|---|---|
|S1|**High (security)**|The API token is given out with no auth: `GET 127.0.0.1:8765/` → 307 `Location: http://localhost:3001?token=<token>`, and `GET localhost:3001/api/token` → `{"token":…}` (only `Sec-Fetch-Site: cross-site` is blocked). Any local process or user can take full API control, including the MCP command execution in #4|`main.py` root route; `dashboard/app/api/token/route.ts`|
|S2|**High (security)**|Still possible to run any command through the MCP API with an allowlisted interpreter plus arbitrary `args` (`python3 -c`, `node -e`, `npx <any package>`, `uvx …`), and the basename-only check accepts `/tmp/fake/python`. Combined with S1, there's no real barrier|`main.py save_mcp_server`|
|S3|Medium (security)|`require_token` accepts `?token=` on **every** endpoint. Launcher, tray and run.ps1 put it in URLs, so it ends up in browser history and the uvicorn access log (confirmed: `GET /api/sessions/1/audio/them?token=…`). The dashboard never removes it from the address bar|`security.py`, `app.py`, `tray.py`, `run.ps1`, `lib/api.ts`|
|S4|Medium (security)|A `?token=` in a dashboard URL overwrites the stored token (confirmed with `ATTACKER-SUPPLIED`). A crafted link breaks the dashboard with no sign of what happened|`lib/api.ts getStoredToken`|
|N5|**High**|The global exception handler crashes (`JSONResponse` is never imported). All unhandled errors become plain-text 500s without CORS, so the UI shows "Failed to fetch". ruff F821 catches it|`main.py:473-483`|
|N6|Medium (privacy)|Recording consent is bypassed: `SessionManager.start(consent_confirmed=True)` is the default, and voice, tray and Meet hard-code `True`. API callers that leave out the field record without confirming consent|`session.py`, `voice/assistant.py`|
|N7|Medium|MCP `list_unread_emails` needs Gmail (never requested), and `get_calendar_events` reads `calendarId="primary"` (only `calendar.app.created` + `calendarlist.readonly` are requested). Both fail even after login|`mcp/servers/workspace.py` vs `integrations/google.py` scopes|
|N8|Medium|The MCP management UI was removed from the Tools page. The navbar still says "Tools & MCP", and Overview links to "MCP Tools Hub →". MCP can only be managed through the API now|`app/tools/page.tsx`, `Navbar.tsx`, `app/page.tsx`|
|N9|Medium|The shipped MCP default `command: "python"` fails on Linux (ENOENT). On Windows it uses system Python without the venv's packages. `POST /api/mcp/servers` returns `status: ok` even when the connect fails|`mcp/manager._ensure_default_config`, `main.py`|
|N10|Low|An MCP tool's "Google account not logged in" response comes back with `isError: false`. Malformed JSON-RPC input is dropped silently instead of returning -32700|`mcp/servers/workspace.py`|
|N11|Low|`/api/integrations/google/exchange` doesn't consume its pending PKCE entry and doesn't check `state`, so a pending login can be reused (the token is still required)|`main.py` exchange|
|N12|Low/Medium|Reprocessing a lecture deletes and recreates Tasks, Notes, Flashcards and Quiz items, which loses status changes you made by hand (done → inbox, confirmed)|`pipelines/lecture.py`|
|N13|Low|Two same-day lectures with the same title overwrite each other's Obsidian note. Windows reserved names (CON, NUL…) aren't handled|`integrations/obsidian.py`|
|N14|Low|Assignments: picking a `.exe` just disables Analyze, with no message|`app/assignments/page.tsx`|
|N15|Low|When `/api/status` gets a 401, the navbar shows "Connecting…" forever, and the dashboard shows no "invalid token" banner anywhere|`Navbar.tsx`, `app/page.tsx`|
|N16|Low|Tools "Connect" always shows "Google sign-in opened in your browser", even when the backend couldn't open one. It does fall back to `window.open`|`app/tools/page.tsx:159-162`|
|N17|Low|Voice "quiz me" with an unknown course silently quizzes on all courses|`voice/assistant.py`|

## Controls, page by page (Playwright)
Key: **Real** = calls the backend and works end to end. **UI** = client-only by design. **Placeholder** = looks functional but doesn't do what it implies. **Broken** = fails.

| Page | Control | Result |
|---|---|---|
|Overview `/`|Manual Rec / Join Meet tabs|UI|
||Join Meet & auto-record|**Broken** on this box: Chrome is missing, so the plain 500 shows as "Failed to fetch" (N5). Calls the real API|
||App tiles ×6 (Chrome, VS Code, Explorer, Terminal, Calculator, Obsidian)|Real `POST /api/integrations/apps/launch`. Windows-only, with no success or error feedback on Linux|
||Mark Done|Real `POST /api/tasks/{id}/status`|
||Links: Live, Tools, Lectures, Lecture N, Tasks|OK|
||"MCP Tools Hub →"|**Placeholder**: leads to the Tools page, which has no MCP section (N8)|
|Live `/live`|All / Instructor / You|UI filter, works|
||Add timestamp bookmark|**Placeholder-ish**: client state only, lost on reload, never saved|
||Copilot talking points|Real `/api/copilot/suggest`|
||Copy point|Clipboard, works|
||Ask Eve (submit)|Real `/api/voice/interact`|
||STOP & ANALYZE|Real: stops, processes, opens the lecture|
||Copilot collapse (icon)|UI; no aria-label or title|
|Lectures `/lectures`|Search, Course filter|UI filter, correct (5 / 1 / 0 / 3 results)|
||New Session link|OK|
|Lecture `/lectures/1`|Transcript / Notes / Flashcards / Quiz tabs|UI over real data|
||Play / seek / timestamps / range|Real audio, works|
||Speaker / Mic source|Speaker works. Mic returns 404 with no message when there's no `me.wav`|
|`/lectures/abc`|—|"Lecture not found" + Return link|
|Tasks `/tasks`|Sync Google|Real; shows "Google account not authenticated" (correct when not logged in)|
||Confirm Task / Start Doing / Directly mark done|Real, all work|
||Course filter|Real `GET /api/tasks?course=`|
|Assignments `/assignments`|Paste text / Upload mode toggles|UI|
||Analyze (text)|Real; result rendered (mock LLM)|
||Upload (.txt/.pdf/.docx)|Real upload. A `.exe` is silently disabled (N14)|
||Copy draft|Works|
|Tools `/tools`|Refresh status|Real `GET /google/apps`|
||Choose client_secret.json → "Save & enable Google apps"|Real; tested with a fake client. Saves, then Connect becomes enabled|
||Connect (×5)|Real `POST /google/connect` → Google consent URL with state+PKCE. Can't finish without a real account|
||Sync assignments / Create Meet link / Show recent docs / Show recent files / Push deadlines|Disabled until connected. **Not invoked**: they need Google login, and Create Meet / Push deadlines would be external writes|
||Join class & record dialog|Real; URL validation correct (evil URLs rejected). Launch is **Broken** here, as with Overview|
||Open vault|Real; shows "[Errno 2] No such file or directory: 'cmd'" on Linux (Windows-only)|
||Google Cloud Console link|OK (external link)|
|Chat `/chat`|Suggestion chips|UI (fill the input)|
||Send|Real `/api/chat`; cited answer with Markdown|
||Course filter|Works|
|Settings `/settings`|Save Token|Real; checks the token|
||Eye toggles|UI|
||Save & Activate API Keys|Real; disabled while empty, persists (#7)|
||Sign in with Google|Disabled until configured|
||Simulate "Hey Eve"|Real `POST /api/voice/wakeword/trigger`; **no visible feedback**|
||Refresh Devices|Real|
||Purge Expired Audio|Real; "Purged 0 …"|
||Get Free Key links|OK (external)|

## Login and auth details
- No token and wrong token: 401 on every `/api/*` route. `/health` is open (fine). The Google callback is open but checks state (400 page).
- `/` (backend) and `/api/token` (dashboard) are open and **reveal the token** (S1).
- WebSocket `/ws/live`: missing or wrong token gets close code 4401, evil Origin gets 403, and the right token gets "hello".
- LocalOnlyMiddleware: foreign Host/Origin is rejected (as in v1).
- Persistence: the token stays in localStorage across reloads. A fresh profile auto-fetches it from `/api/token`.
- Logout: **none**. Clearing storage logs you straight back in.
- Wrong stored token: silent zeros, no banner, "Connecting…" forever (N15). The Settings save check does catch it.

## MCP details
| Server | Tool | How it was added | Listed | Invocation (safe input) | Status |
|---|---|---|---|---|---|
|google_workspace (`eve.mcp.servers.workspace`)|—|Shipped default (`python`, disabled) → enabled through the API|—|Connect fails: ENOENT 'python' (N9)|Broken as shipped on Linux|
|same, `command=<venv python>`|`get_classroom_assignments(course_name="IT 222")`|`POST /api/mcp/servers`|Yes|"Google account not logged in" (`is_error: false`)|**Untested, needs Google credentials**|
||`get_calendar_events(max_results=3)`|same|Yes|same|Untested (credentials). Also can't work with the new scopes (N7)|
||`list_unread_emails(max_results=3)`|same|Yes|same|Untested (credentials). Gmail scope is never requested (N7)|
||unknown tool|—|—|"not found", `is_error: true`|OK|

The tests only used commands from the repo itself. Nothing external was written. `data/mcp_servers.json` was restored to the shipped default afterwards.

## Tool results
- pytest: 67 passed.
- ruff `--select F,B`: 56 findings. Notable: F821 main.py:473/480 (`JSONResponse`), F811 assistant.py:287. The rest are mostly B008/B904 style.
- bandit `-ll`: no medium/high findings.
- pip-audit: no known vulnerabilities.
- npm audit: 5 high (braces, micromatch via tailwindcss 3 / chokidar); build-time only. Fix: Tailwind 4 or `npm audit fix`.
- detect-secrets: no committed secrets.
- tsc `--noEmit`: clean.
- `npm run build`: OK, 11 routes.

## Suggested fixes (short)
1. Remove the token from the root redirect and `?token=` URLs. Remove `/api/token`, or protect it (for example a one-time code passed from the launcher). Only accept the query token on the audio route.
2. MCP: allow only exact registered server entries (name → fixed command + args, shipped by the app), or require user confirmation in the desktop app. Never accept arbitrary `args` from the HTTP API.
3. `from fastapi.responses import JSONResponse` in main.py, and add ruff F to CI.
4. Default `consent_confirmed` to False, and ask for consent in the voice, tray and Meet flows.
5. Add `gmail.readonly` and the calendar scopes the MCP tools need, or drop those tools. Use `sys.executable` in the default MCP config. Return `isError: true` for auth errors.
6. Bring back an MCP section on Tools, or rename the nav and Overview link.
7. Upsert tasks on reprocess, keeping their status. Add a logout, and an "invalid token" banner.

## Box state
- Running on the box:
  - backend (fake audio) on 127.0.0.1:8765
  - mock Ollama on :11434
  - dashboard on :3001
- Files changed on the box (all gitignored; the git tree is clean):
  - The test DB was reseeded with seed.py; the v1 DB is backed up at `EvE-report/eve-v1.db`.
  - A 1 s silent `them.wav` was added for session 1.
- Cleaned up after testing:
  - the fake client secret (deleted)
  - the test Groq key (removed from `.env`, backend restarted)
  - `/tmp/eve_pwned` (deleted)
  - the MCP config (reset to default)
- Screenshots: `/workspace/EvE-report/screenshots-v2/` (72 files: page_*, click_*, auth_*, tools_*, lectures_abc, chat_answer, assignments_*).
- Harness scripts: `/workspace/EvE-report/harness/`.
