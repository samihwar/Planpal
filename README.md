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

## Run the app

```bash
python main.py
```

Open `http://localhost:8000` on a PC, or open the same address from a phone on your local network. In Chrome, Edge, or supported mobile browsers, use the in-app install button or the browser install option to add PlanPal to your home screen or desktop.
