# E.V.E. (Extensible Virtual Entity)

> **Local-First AI Study & Work Assistant**  
> Attends online lectures, transcribes mixed Bisaya/English/Tagalog speech, generates structured Obsidian notes, tracks coursework deadlines, and assists your daily study workflow.

---

## Architecture Overview

1. **Audio Capture**: Windows WASAPI Loopback (`PyAudioWPatch`) captures system sound (Zoom, Google Meet, Teams, Discord, YouTube) and default microphone in time-aligned, zero-padded WAV streams.
2. **Speech-to-Text (STT)**: `faster-whisper` (`large-v3-turbo` on RTX 4060 GPU / CPU fallback) with streaming Silero VAD chunking and Bisaya/Tagalog code-switch prompting.
3. **Intelligence (Hybrid)**: `google-genai` (Gemini 2.5 Flash) for high-fidelity code-switching lecture summaries, flashcards, quizzes, and tasks + offline local Ollama 7B fallback.
4. **Second Brain Integration**: Direct automated note generation into `Obsidian Vault\13 - Lectures\<Course>\`.
5. **Security & Guardrails**: 127.0.0.1 loopback-only API with per-install Bearer tokens, CSRF/DNS-rebinding protection, per-session participant consent confirmation, and read-only Google Classroom access (zero auto-submissions).

---

## Quickstart

### 1. Setup Environment
Open PowerShell and run:
```powershell
.\scripts\setup.ps1
```
This initializes the virtual environment at `.venv`, installs all core dependencies, and provisions the default `.env`.

### 2. Configure Your Gemini API Key
To keep your key safe from Git and accessible to both E.V.E. and your terminal, set it as a Windows User environment variable:
```powershell
[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "your_gemini_api_key_here", "User")
```
Restart your terminal after setting the variable for it to take effect.

### 3. Check Audio Devices
List all audio hardware, default input microphones, and WASAPI loopback endpoints:
```powershell
.\scripts\run.ps1 -Mode devices
```

### 4. Test Live Captions in Terminal
Test real-time speech transcription right in your PowerShell console:
```powershell
.\scripts\run.ps1 -Mode live -Title "Networking Lecture" -Course "IT 222"
```
Play any video or lecture audio, or speak into your microphone. You will see real-time captions tagged with `THEM` (system loopback) or `ME` (microphone).

### 5. Launch the Local API Server
Start the local FastAPI server:
```powershell
.\scripts\run.ps1 -Mode serve
```
The server will run on `http://127.0.0.1:8765`. Your per-install API token is stored in `data\api_token`.

---

## Second Brain (Obsidian) Connection

E.V.E. is linked to your Obsidian Second Brain:
- **Project Hub**: `C:\Users\Legion\Documents\Obsidian Vault\01 - Projects\E.V.E\E.V.E.md`
- **Active Plan**: `C:\Users\Legion\Documents\Obsidian Vault\01 - Projects\E.V.E\Active-Plan.md`
- **Lecture Outputs**: `C:\Users\Legion\Documents\Obsidian Vault\13 - Lectures\<Course>\YYYY-MM-DD - <Title>.md`

---

## Verification & Tests

To execute the test suite:
```powershell
.\.venv\Scripts\python -m pytest backend/tests -v
```
