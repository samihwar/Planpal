# Planpal

Planpal is an AI-powered personal task and schedule manager. It parses natural language input into structured tasks and can optionally integrate with your calendar.  

This version uses **Ollama LLM** (`llama3`) to parse tasks instead of `dateparser`, allowing more flexible understanding of dates, times, and durations.

---

## Features

- Parse natural language task descriptions into JSON:
  - `title`: short summary of the task
  - `description`: full description
  - `due`: ISO 8601 start timestamp
  - `duration`: task length in hours
- Handles relative dates like "tomorrow", "next Friday", etc.
- Uses a local LLM (`llama3`) for intelligent parsing.
- Configurable for different timezones.
- Installable app experience for desktop and mobile browsers through the included PWA manifest and service worker.

---

## Installation

1. Clone the repository:
```bash
git clone <https://github.com/samihwar/Planpal.git>
cd Planpal
```
2.Set up the Python virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
# or
source .venv/bin/activate # Linux/Mac
```
3.Install dependencies:
```bash
pip install -r requirements.txt
```
3.Install and run Ollama
[https://ollama.com](https://ollama.com)
```bash
ollama run llama3
```

## Open PlanPal

Start the local server from the project folder:

```powershell
python main.py
```

### Open on this PC

After the server starts, open:

```text
http://localhost:8000
```

Chrome or Edge can install the desktop PWA from the browser menu or the in-app install button.

### Open on a phone with HTTPS

Phone PWA install prompts usually need HTTPS. For local testing, use Cloudflare Tunnel to create a temporary HTTPS link to the app running on this PC.

Keep `python main.py` running, then open a second PowerShell window and run:

```powershell
C:\Users\samih\Downloads\cloudflared-windows-amd64.exe tunnel --url http://localhost:8000
```

Cloudflare will print a temporary link like:

```text
https://example-words.trycloudflare.com
```

Open that HTTPS link on the phone. In Chrome, open the three-dot menu and choose **Install app**. If Chrome only shows **Add to Home screen**, wait for the page to finish loading, tap the in-app install button, then check the Chrome menu again.

### Stop the Cloudflare tunnel

To see running tunnel processes:

```powershell
Get-Process cloudflared-windows-amd64
```

Stop one tunnel by process id:

```powershell
Stop-Process -Id <PROCESS_ID>
```

Or stop all running Cloudflare tunnel processes:

```powershell
Stop-Process -Name cloudflared-windows-amd64
```

Quick Cloudflare Tunnel links are temporary. Each time you stop and start the tunnel, Cloudflare will usually give you a new HTTPS link.
