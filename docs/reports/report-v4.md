# E.V.E. test report, fourth pass (v4)
Date: Mon 19 Oct 2026 (Asia/Manila, UTC+8). Repo: JoeSecondBrainVault/EvE @ `b32316d`. Nothing was pushed; the remote was not changed.

## Summary

**New commits:** 2, fast-forwarded cleanly from `3eda65c`.
1. `824e525`, **2026-10-19 9:23:47 PM UTC+8**, Joebelle-01. "fix(security): resolve report-v3 S2/#4, N18, N19, N6/N7 residuals, and accessibility". 13 files, +242 / −69. No dependency changes.
2. `b32316d`, **2026-10-19 9:32:14 PM UTC+8**, Joebelle-01. "docs: archive test and security audit reports v1, v2, and v3". Adds `docs/reports/report-v{1,2,3}.md` only.

**Fixed vs still open (v3 open items):**
| Item | v4 status |
|---|---|
|**S2/#4** five arg/runtime bypasses (`-c<code>`, `-Ic`, `.py` path, venv+`-c`, `node -p`)|**Fixed** (all five return 400; no marker files). **New residual HIGH: unvalidated `env`** (see S5) |
|**N18** save-before-connect|**Fixed** for `enabled=true` failures (broken server not persisted). Disabled saves still persist (expected). Env payloads that *succeed* at connect still persist (S5) |
|**N19** hardcoded Legion vault|**Fixed** — default is `Path.home()/"Documents"/"Obsidian Vault"`; exposed via `/api/status.vault_path` and Settings UI |
|**N6** consent auto-true|**Mostly fixed** (voice tools require `consent_confirmed`; CLI prompts; Meet API gated). **Residuals:** UI checkboxes default checked; `startSession()` always sends `true`; tray on non-Windows auto-consents; `main.py` tray callback still hardcodes `True` |
|**N7** Gmail connect|**Fixed** — `app=gmail` accepted; Gmail card + "List unread emails" on Tools; scopes include `gmail.readonly` |
|**#28** Ollama 7B label|**Fixed** — now "Local Offline LLM" |
|**Live Bookmark** not saved|**Fixed** — persisted in `localStorage` (`eve_live_bookmarks`), restored on reload; Copilot collapse has `aria-label` |
|**#35** npm audit|**Still open** — 5 high (Tailwind 3.4.19 / micromatch / braces), build-time |

**New bugs / security this pass:**
- **S5 (HIGH):** MCP `env` is completely unvalidated. `PYTHONPATH=/tmp/...` + a `sitecustomize.py` ran arbitrary code during connect (marker file written: "sitecustomize ran"), and the API returned `status: ok` and persisted the hostile env. `PYTHONSTARTUP`, `LD_PRELOAD`, etc. are also accepted. This bypasses the new command/args pin.
- **N20 (Medium):** `MCPManager.load_servers()` on startup does **not** re-apply the API allowlist. A hand-edited or previously saved `mcp_servers.json` with hostile `command`/`args`/`env` will still be launched.
- **N6 residuals (Low):** UI consent defaults to checked; dashboard `startSession()` hardcodes `consent_confirmed: true`; Linux tray path sets `consent = True` without a prompt; `main.py` `tray_enabled` lambda still passes `consent_confirmed=True`.

**Security overall:** The five v3 arg/runtime RCE bypasses are closed. Token leak (S1), URL token (S3/S4), and OAuth replay stay closed. The remaining MCP RCE surface is the unrestricted `env` map (S5) plus no re-validation on load (N20). pip-audit and bandit are clean.

**Buttons (Playwright, 97 controls):** Every button has a handler; no dead/placeholder buttons.
- Real: app tiles, Meet (500 Chrome-missing, proper message), Copilot, Ask Eve, lecture tabs/audio, Tasks Sync/status, Assignments, chat, Settings Save/Logout/Simulate/Purge, Tools refresh, MCP Enable/Disable/Test Call (verified separately), Gmail card (Connect + List unread, gated until linked).
- Was-placeholder, now real: Live bookmarks (persist across reload).
- UI-only by design: filters, tabs, eye toggles, suggestion chips.
- Broken(env) only: Meet launch / Open vault / app tiles on this Linux box.

**Login:** Missing and wrong token → banner + Auth Error footer. Valid token works and persists. Logout clears storage and stays logged out (no silent re-login). `?token=` no longer overwrites an existing token and is stripped from the URL. Protected `/api/*` still require the bearer token; `?token=` only on audio routes.

**MCP:** One shipped server `google_workspace` (3 tools). Enabled via Tools → MCP Hub and via API; all 3 tools listed; each Test Call / `/api/mcp/call` with safe inputs returns "Google account not logged in", `is_error=true`. Untested vs real Google data (no credentials). Config restored to shipped default afterward.

**Tests:** pytest **67 passed**. ruff F clean; 14 B008 only. tsc clean. build OK. pip-audit clean. npm audit: **5 high** (unchanged).

---

## New commits (detail)
| Hash | Time (UTC+8) | Author | Message | Diff |
|---|---|---|---|---|
|`824e525`|2026-10-19 21:23:47|Joebelle-01|fix(security): resolve report-v3 S2/#4, N18, N19, N6/N7 residuals, and accessibility|13 files, +242/−69|
|`b32316d`|2026-10-19 21:32:14|Joebelle-01|docs: archive test and security audit reports v1, v2, and v3|+560 (docs only)|

Key changes in `824e525`: MCP args pinned to exactly `["-m","eve.mcp.servers.<module>"]` with module file existence check; only venv Python allowed; connect-before-persist; vault_path via `Path.home()`; voice/CLI consent gates; Gmail in connect pattern + Tools card; "Local Offline LLM"; Live bookmarks + aria-label.

## Recheck of every v3 open item
| Item | Status | Evidence |
|---|---|---|
|S2 #1 glued `-c<code>`|**Fixed**|400 "Disallowed arguments…"; no `/tmp/eve_v4_1`|
|S2 #2 `-Ic`|**Fixed**|400; no marker|
|S2 #3 `.py` script path|**Fixed**|400; no marker|
|S2 #4 venv abs + `-c`|**Fixed**|400; command rewritten to sys.executable but args still rejected|
|S2 #5 `node -p`|**Fixed**|400 "Disallowed command runtime: 'node'"|
|Extra: `-m`+extra args, module traversal, nonexistent module, `uvx`, bad name|**Fixed**|all 400|
|**S5 env injection (new)**|**Open HIGH**|`env.PYTHONPATH` + sitecustomize → code ran; status ok; entry persisted|
|N18 failed enable|**Fixed**|`eve.mcp.servers.broken` enabled → status error; config still only `google_workspace`|
|N19 Legion path|**Fixed**|default `/home/box/Documents/Obsidian Vault`; status + Settings show `/workspace/EvE-run/vault` under test override|
|N6 voice|**Fixed**|`_tool_start_session` without consent → `consent_required`; meet without consent → `recording=False`|
|N6 API|**Fixed**|`POST /sessions/start` without consent → 409|
|N6 UI defaults|**Residual**|Overview Meet/Manual Rec and Tools Meet checkboxes default **checked**|
|N6 tray/CLI residuals|**Residual**|Linux tray `consent=True`; `main.py:423` hardcodes True; `api.ts startSession` always sends true|
|N7 Gmail|**Fixed**|connect 200, scope has gmail.readonly; apps list includes gmail; Tools shows Gmail + List unread emails|
|#28|**Fixed**|"Ollama 7B" gone; "Local Offline LLM" shown|
|Live Bookmark|**Fixed**|`localStorage eve_live_bookmarks` set; survives reload; UI shows "Bookmarked moments"|
|Copilot aria|**Fixed**|`aria-label="Collapse Live Copilot"`|
|#35|**Open**|npm audit 5 high (tw 3.4.19)|

## New findings
| ID | Sev | Bug | Evidence |
|---|---|---|---|
|S5|**High**|MCP `env` dict is unrestricted. Attacker with API token sets `PYTHONPATH` (or `PYTHONSTARTUP` / `LD_PRELOAD`) and runs arbitrary code in the MCP child; connect often still succeeds so N18 persists it|`MCPServerConfig.env`; client merges into `os.environ`; reproduced with sitecustomize writing `/tmp/eve_v4_envA`|
|N20|Medium|`load_servers()` launches whatever is in `mcp_servers.json` with no re-validation of command/args/env|`mcp/manager.py:47-60`|
|N6 residual|Low|Consent UX is opt-out (pre-ticked) and several call sites still force `true`|`page.tsx`/`tools/page.tsx` `useState(true)`; `api.ts:210`; `cli.py` non-win32; `main.py:423`|

## Controls (Playwright)
97 controls across 9 pages. Highlights vs v3:
- Live "Add timestamp bookmark" → now persists (Real client+storage).
- Live Copilot collapse → labeled "Collapse Live Copilot".
- Tools: Gmail Connect + List unread emails (disabled until linked).
- Tools MCP Hub: Enable/Disable/Refresh/Test Call work (Test Calls also verified manually after Enable).
- Settings Log Out → clears token; stays logged out.
- Meet Join still Broken(env) with clear Chrome error (CORS OK).

## Login
- Missing / wrong → Invalid API Token banner + Auth Error (401).
- Valid → works; persists across reload.
- Logout → storage null; banner on `/`; no auto re-login.
- S4 still held: existing token not overwritten by `?token=ATTACKER`; param stripped from URL.

## MCP
| Server | Tool | Via | Result |
|---|---|---|---|
|google_workspace|get_classroom_assignments|UI Enable + API call|is_error true, not logged in|
||get_calendar_events|same|same|
||list_unread_emails|same|same|

Only repo-shipped modules accepted. Hostile env entries cleaned; config restored to shipped default (disabled).

## Tooling
- pytest: 67 passed (with mock Ollama unreachable so embeddings use the real offline path).
- ruff F: clean. F,B: 14 B008.
- bandit -ll: clean. pip-audit: no known vulns.
- tsc: clean. `npm run build`: OK. npm audit: 5 high.

## Recommended fixes
1. **S5 (HIGH):** reject or ignore client-supplied `env` entirely (or allowlist only harmless keys). Never pass attacker-controlled `PYTHONPATH`/`PYTHONSTARTUP`/`LD_PRELOAD` into the MCP child.
2. **N20:** run the same command/args/(env) validation inside `load_servers` before connect; refuse to launch non-conforming entries.
3. N6 residuals: default consent checkboxes to **unchecked**; pass the UI consent flag into `startSession`; prompt on Linux tray; remove the hardcoded `True` in `main.py` tray lambda.
4. #35: upgrade Tailwind to v4 (or `npm audit fix`).

## Box state
- Running: backend (fake audio, `EVE_VAULT_PATH=/workspace/EvE-run/vault`) :8765; mock Ollama :11434; dashboard :3001.
- Repo at `b32316d`; git status clean after cleanup.
- Cleaned: hostile MCP entries, fake client_secret, `/tmp/eve_v4_*`, backend restarted so in-memory MCP clients are gone. `mcp_servers.json` = shipped default (disabled).
- Screenshots: `/workspace/EvE-report/screenshots-v4/` (auth_*, settings, tools_*, live_bookmarks, crawl set).
