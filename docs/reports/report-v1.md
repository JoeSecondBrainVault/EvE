# E.V.E. test report
Repo: JoeSecondBrainVault/EvE (private), commit `cdf688c`, tested 2026-10-19 ~2:08–2:20 PM (UTC+8) on the Linux box (not on Joe's PC). Nothing was pushed or changed on the remote.

## What the app is
**E.V.E.** is a local-first Windows study assistant. It records lecture audio (WASAPI loopback + mic), transcribes it with faster-whisper, writes Obsidian notes, tasks, flashcards and quizzes using Groq, Gemini or Ollama, and offers RAG chat, Google Classroom/Calendar sync, a voice assistant, Meet auto-join and MCP tools.

| Part | Stack | How it runs |
|---|---|---|
| Backend | Python 3.12–3.13, FastAPI/uvicorn, SQLModel + SQLite, faster-whisper | `python -m eve serve` → http://127.0.0.1:8765 (Bearer token in `data/api_token`) |
| Dashboard | Next.js 16 / React 19 / Tailwind 3 | `npm start -- -p 3001` (desktop launcher) or `npm run dev` (port 3000) |
| Desktop | pywebview window + pystray tray (Windows only) | `python -m eve app` starts the backend and dashboard, then opens a window |

### Box limitations (not bugs in the app)
Audio capture (`pyaudiowpatch`), pywebview, the tray, Chrome/Meet and app launching (`cmd`, `calc.exe`) are Windows-only, so these were exercised only up to their error paths. No Ollama, Gemini or Groq was available, so LLM features were tested for error handling only, plus logic checks with a fake router (`probe_assistant.py`). STT ran with Whisper `tiny` on CPU.

### Still running on the box
- Backend: http://127.0.0.1:8765 (log `EvE-report/backend.log`)
- Dashboard: http://localhost:3001 (log `EvE-report/dashboard.log`)
- Test data seeded with `EvE-report/seed.py` (DB at `/workspace/EvE/data/eve.db`)

## Install / build / test / lint results
| Step | Result |
|---|---|
| `pip install -e backend[dev]` (Linux, Py 3.13) | **FAIL**: `ERROR: No matching distribution found for tflite-runtime<3,>=2.8.0; platform_system == "Linux" (from openwakeword)`. This only affects Linux/Python 3.13; Windows is fine. Box workaround: install everything else, then `openwakeword --no-deps`. |
| `npm ci` | OK. `npm audit`: **5 high** (braces/micromatch/chokidar via tailwindcss 3). The `overrides` in package.json don't clear them. |
| `npx tsc --noEmit`, `npm run build` | OK. All 10 routes build. |
| `npm run lint` | **FAIL**: `Invalid project directory provided, no such directory: /workspace/EvE/dashboard/lint`. Next.js 16 removed `next lint`, and there's no ESLint config. |
| `pytest -m "not gpu"` | **66 passed, 1 failed**: `test_keyring_token_storage` fails here because Linux has no keyring backend. See bug #8 for why this test is dangerous on Windows. The process also prints `terminate called without an active exception` at exit, so a native thread isn't shut down cleanly. |
| `ruff --select F,B` | 62 issues, mostly unused imports/variables (e.g. `pipelines/assignments.py:135` `rag_citations` is unused, so citations are computed and then thrown away). Bandit: one Medium (B310 urlopen in `app.py:29`, low risk). |
| Secrets scan (detect-secrets + git history) | **Clean.** No real API keys, client secrets or `.env` were ever committed. |

## Bug list (prioritized)
Severity: **Critical** = core feature broken / security; **High** = feature broken; **Medium** = wrong behaviour / bad UX; **Low** = polish.

### Critical
1. **Stopping a recording never generates notes and never opens the lecture.**
   - **Where:** `dashboard/app/live/page.tsx:136-139` and `lib/api.ts:181`.
   - **What happens:** The backend `/api/sessions/stop` returns a `SessionOut` with **`id`**, but the UI reads `res.session_id`, which is `undefined`. So `processSession()` and the redirect to `/lectures/<id>` never run, and the main "record → notes" workflow silently does nothing after Stop.
   - **Repro:** start a session on Live and click Stop.
   - **Expected:** the session is processed and the lecture page opens.
   - **Fix:** use `res.id`.
2. **The lecture audio player can never play.**
   - **Where:** `lib/api.ts:248` builds `.../audio/them?token=...`, but `security.py:41-50` accepts **only** an `Authorization` header.
   - **Verified:** `GET /api/sessions/1/audio/them?token=<valid>` returns **401**. In the browser it shows as `net::ERR_BLOCKED_BY_ORB` on `/lectures/1`.
   - **Repro:** open any lecture and press Play.
   - **Fix:** fetch the audio with the header and play it from a blob URL, or accept a short-lived signed query token on that one route.
3. **Any unhandled backend error shows up as "Failed to fetch".** Because of CORS, the real error message never reaches the UI.
   - **Where:** `main.py` routes that don't catch exceptions: `voice_interact:857`, `launch_meet:969`, `google_auth_url:704`, `google_exchange:718`, `google_callback:757`, `save_mcp_server:998`.
   - **Why:** Starlette's 500 response is produced outside `CORSMiddleware`, so it has no `Access-Control-Allow-Origin` header. Verified: a 500 from `/api/voice/interact` has no CORS header, while handled `HTTPException` 500s do.
   - **Repro:** Overview → Google Meet → enter `abc-defg-hij` → Join. The red box says "Failed to fetch" (`screenshots/C_meet_launch.png`). The same happens with "Ask Eve" on Live when no LLM is running.
   - **Fix:** wrap these routes in try/except → `HTTPException`, or add a global exception handler.
4. **Security: arbitrary commands can be launched through the MCP API.**
   - **Where:** `main.py:993-1000` with `mcp/manager.py:109-135`.
   - **What happens:** POST `/api/mcp/servers` with `{"command": "...", "enabled": true}` immediately `Popen`s that command, so anything holding the token gets code execution. The token is in `localStorage` (`lib/api.ts:118`), so any XSS on the dashboard is a full system compromise.
   - **Suggested fix:** require confirming the command in the UI, or restrict it to an allowlist.
   - Body validation errors (`{"name":"x"}`) return a raw 500.

### High
5. **Voice "start recording" always fails.**
   - **Where:** `voice/assistant.py:189` calls `session_manager.start(title=..., course=...)` without `consent_confirmed`.
   - **What happens:** the result is a `TypeError`, and the assistant says "I encountered an issue executing that command: … missing 1 required keyword-only argument: 'consent_confirmed'" (reproduced in `probe_assistant.py`).
6. **Meet auto-record never starts recording, and neither does the Tray "Start session".**
   - **Meet:** `main.py:972` and `voice/assistant.py:322` call `start(title=..., consent_confirmed=True)` without the required `course` keyword → `TypeError`, which is swallowed into `recording_error`. Chrome opens but nothing is recorded.
   - **Tray:** `main.py:410` calls `start("Tray Session", consent_confirmed=True)` with a positional title, but `SessionManager.start` is keyword-only (`session.py:93`) → `TypeError`, so the Tray Start button can never work.
   - **Fix:** pass `course=None`, and use `title=` as a keyword in the tray call.
7. **API keys saved in Settings are lost after a restart.**
   - **Where:** `main.py:816,824` write `GROQ_API_KEY` / `GEMINI_API_KEY` to `.env`, but `Settings` uses `env_prefix="EVE_"` (`config.py:111-116`). It only reads `EVE_GEMINI_API_KEY` from `.env`, and pydantic-settings doesn't export `.env` into `os.environ`.
   - **Verified:** a `.env` containing the saved keys gives `resolved_gemini_api_key=None` after restart.
   - **Repro:** Settings → paste a Groq key → Save → restart E.V.E. → the key shows "Not set".
   - **Fix:** write `EVE_GROQ_API_KEY` / `EVE_GEMINI_API_KEY`, or `load_dotenv()` at startup.
8. **Running the test suite on your PC deletes your real Google login.**
   - **Where:** `tests/test_phase4_google.py:27-33` uses the real keyring service `eve-assistant` and ends with `clear_refresh_token()`.
   - **What happens:** `pytest` signs you out of Google Classroom/Calendar every time it runs.
   - **Fix:** mock `keyring` or use a test-only service name.
9. **Re-processing a lecture duplicates its tasks, flashcards and quiz items.**
   - **Where:** `pipelines/lecture.py:97-150` deletes and replaces the old `Note`, but appends new `Task`/`Flashcard`/`QuizItem` rows without deleting the old ones.
   - **Repro:** click "Process"/"Generate notes" twice on the same lecture.
10. **Every failed recording start leaves a junk "failed" lecture behind.**
    - **Where:** `session.py:151` marks the row `failed` but keeps it.
    - **What happens:** it appears in Lectures and counts toward "Recorded Lectures" on Overview. In my test it went from 2 to 4 after two failed starts (`screenshots/C_meet_launch.png`).
11. **The Google OAuth callback is unauthenticated and has no `state` check.**
    - **Where:** `main.py:751-771`.
    - **What happens:** any page you visit can redirect you to `/api/integrations/google/callback?code=<attacker code>`, linking the attacker's Google account (login CSRF). It also registers an MCP server with `command="python"` (`main.py:765`). On Windows that is the system Python, not `.venv`, so `-m eve.mcp.servers.workspace` probably fails to import.
    - **Fix:** use `sys.executable` and validate an OAuth `state`.
12. **Google endpoints crash with a raw 500 when OAuth isn't configured.**
    - **Where:** `auth-url`, `exchange` and `callback` (`main.py:704,717,756`).
    - **What happens:** `ValueError: Google OAuth credentials not configured` propagates, and the UI shows "Failed to fetch".
    - **Fix:** return a 400 with that message.

### Medium
13. **No-token first run looks like an empty app.** Before the token is pasted in Settings, Overview shows 0 everywhere and Lectures says "No lectures found". All 401s are swallowed (`app/page.tsx:71-74`). `/lectures` also throws an uncaught promise rejection ("Missing or invalid API token"). There's no "connect your token" prompt. Screenshots: `A_notoken_.png`, `A_notoken_lectures.png`.
14. **`/lectures/abc` (non-numeric id) shows "Loading lecture details…" forever.** `Number("abc")` is NaN and is never handled (`lectures/[id]/page.tsx:39`). Screenshot: `B_lectures_abc.png`.
15. **Voice "summarize my last lecture" with no notes gives an error message.** `assistant.py:267` returns no `title`, so `:138` raises `KeyError 'title'`, and the user hears "I encountered an issue executing that command: 'title'".
16. **Voice "quiz me" has three problems:** it ignores the course argument (`assistant.py:274-277`), returns `options` as a raw JSON string instead of a list (`:285`), and with no quizzes says "Here is a question on your coursework: No quiz items generated yet…".
17. **Voice "stop recording" returns the whole Session object as `session_id`** (`assistant.py:195-196`), because `stop()` returns a row, not an id.
18. **The app-launcher allowlist matches substrings** (`assistant.py:365-367`). `"decode this"` matches `code` and launches VS Code. Verified via `/api/integrations/apps/launch`. Use exact matches.
19. **`normalize_meet_url` passes through any `http(s)` URL** (`integrations/chrome.py:478-486`). The voice or Meet form can open arbitrary sites in your logged-in Chrome profile. Restrict it to `meet.google.com`.
20. **Error messages are misleading when no LLM is available.** They always say "Both Gemini and local Ollama failed…" even when Gemini/Groq were never configured (`llm/router.py:157`). Screenshot: `C_assignments_analyze.png`.
21. **Dashboard port mismatch.** The backend redirects `/` and the Google OAuth callback to **:3001** (`main.py:463,771`). But `run.ps1 -Mode dashboard` and `npm run dev` use **:3000**, and the tray "Open Dashboard" opens :3000 (`tray.py:59`). In dev mode, the Google connect flow lands on a dead page.
22. **The desktop launcher assumes a production build exists.** `app.py:100` runs `npm start` without `next build`, so on a fresh clone the window opens on nothing. It also treats *any* service on :3001/:3000 as the dashboard.
23. **Search `top_k` is unbounded on `/api/chat/search`** (`main.py:630`, `top_k=100000` and `-1` are accepted). `/api/chat` limits it to 1–10.
24. **Audio file lookup can return another session's recording.** It uses `glob("*-{id}-*")` (`main.py:652`), so session 1 also matches folders like `…-5-Lecture-1-intro`. Use the stored `Session.recording_dir` instead.
25. **MCP client stderr is piped but never read** (`mcp/client.py:45-55`). A chatty server fills the pipe and hangs.
26. **The rate limiter claims to be thread-safe but has no lock** (`retention.py:40-70`), and sync routes run in a threadpool.
27. **An empty session note says "Instructor 0% / You 100%"** (`obsidian.py:98-99`). Processing a session with 0 segments still writes a note to the vault.

### Low
28. **Hardcoded UI text** doesn't reflect the real state: "Welcome back, Joe", "on your Legion RTX 4060", and Intelligence "Local Ollama 7B" (shown even when Ollama isn't running).
29. **Chat answers show raw Markdown** (`**IT 222 (00:00)**`). Screenshot: `C_chat_answer.png`.
30. **Settings "Save Token" always says "Token saved successfully. Backend requests authorized."** without testing the token.
31. **The task card shows `Low confidence (quote: "...")`** for tasks with no evidence (Overview).
32. **The TS `Session.status` type** (`idle|processing|error`) doesn't match the backend (`stopped|failed|processed`) (`lib/api.ts:11`).
33. **The README `run.ps1 -Mode live --Title ...` example is wrong;** the script parameter is `-Title`. `eve tray` standalone has no start/stop callbacks, so those menu items do nothing (`cli.py:248`).
34. **`assignments` text mode:** the Analyze button isn't disabled when the text is empty.
35. **`tsconfig.tsbuildinfo` isn't in `.gitignore`.** There are 5 high npm audit findings (upgrading to Tailwind 4 fixes them). `next lint` is removed in Next 16.

## What works well
- **Auth/Host/Origin hardening works:** no token → 401, bad Origin → 403, bad Host → 400.
- **Validation works:** consent is enforced on manual start, and task status, 404s and the upload extension/size checks behave correctly.
- **Pages render correctly:** the lecture page (transcript, note, flashcards, quiz tabs) and the Tasks page.
- **Search works:** RAG keyword chat finds and cites seeded lecture text after indexing, and the 404 page and "Lecture not found" render properly.

## Local changes made on the box (not committed or pushed)
- Created `.venv` and `node_modules`. Installed `openwakeword` with `--no-deps` (Linux only).
- `data/`, `models/` (Whisper tiny) and the seeded DB, all gitignored.
- No source files were modified; `git status` is clean.

## Files
- Screenshots: `/workspace/EvE-report/screenshots/` (28 PNGs: `A_*` no token, `B_*` every route with token, `C_*` interactions)
- Raw browser log: `ui_log.json`; scripts: `ui_test.py`, `probe_assistant.py`, `seed.py`; server logs: `backend.log`, `dashboard.log`
