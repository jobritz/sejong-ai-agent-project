# Studium File Organizer Agent

An agentic AI system that watches `~/Downloads` and automatically sorts
new files into your `~/Studium` semester/lecture folder tree — using a
**fully local LLM** (Llama 3 via Ollama). No API key, no cloud, no cost.

## Project structure

```
file_organizer_agent/
├── main.py               # entry point + CLI
├── config.py             # all settings
├── requirements.txt
├── agent/
│   ├── classifier.py     # file classifier with LLM
│   ├── executor.py       # file mover + undo stack + log writer
│   └── watcher.py        # watchdog event handler
└── utils/
    └── reporter.py       # daily summary report
```

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) installed and running

## Setup (for Windows)

```bash
# 1. Clone / download the project
git clone https://github.com/jobritz/sejong-ai-agent-project

# 2. Create a virtual environment in the project directory
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Ollama and get LLM (e.g. gemma4:e2b)
ollama pull gemma4:e2b

# 5. Create your Studium folder structure
mkdir -p ~/Studium/1.\ Semester/Database\ 1
mkdir -p ~/Studium/1.\ Semester/Operating Systems
# … add as many semesters and lectures as you need

```

No `.env` file or API key is required.

## Usage

```bash
# Watch ~/Downloads (default)
python main.py

# Watch a custom folder
python main.py --watch /path/to/folder

# Print today's summary
python main.py --summary

# Look back 48 hours in the summary
python main.py --summary --hours 48
```

## How it works

1. **watchdog** listens for two events in `~/Downloads`:
   - `on_created` — catches files that appear directly (e.g. copied files).
   - `on_moved` — catches completed downloads. Browsers write a `.tmp` /
     `.crdownload` temp file while downloading, then **rename** it to the
     final filename. Only `on_moved` sees the finished file.
2. Temp and partial files (`.part`, `.crdownload`, `~$…`) are filtered out.
3. A short sleep lets the file finish writing before processing starts.
4. **Content extractor** reads a text snippet from the file:
   - `.pdf` — first pages via PyMuPDF
   - `.docx` — paragraph text via python-docx
   - `.txt`, `.md`, `.py`, `.html`, … — direct read
   - Unreadable files (images, binaries) — filename only
5. **Ollama classifier** receives the text snippet + your real folder tree
   (scanned live from `~/Studium`) and returns:
   - `semester` — exact folder name, e.g. `"2. Semester"`
   - `lecture`  — exact subfolder name, e.g. `"Analysis 2"`
   - `confidence` — float 0–1
   - `reason` — one-sentence explanation
6. **Executor** moves the file to `~/Studium/<semester>/<lecture>/`,
   creates the path if needed, and handles filename collisions.
7. Every move is appended to a JSON-lines log at `~/Studium/organizer.log`.
8. **Undo stack** lets you roll back moves within a session.
9. **Daily summary** is printed at 18:00 and on shutdown.

## Configuration

All settings are in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `WATCH_DIR` | `~/Downloads` | Folder to monitor |
| `STUDIUM_DIR` | `~/Studium` | Root of your lecture folder tree |
| `OLLAMA_MODEL` | `"llama3"` | Any model you have pulled locally |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `MAX_CONTENT_CHARS` | `3000` | Text chars sent to the LLM per file |
| `CONFIDENCE_THRESHOLD` | `0.60` | Below this → placed in `_Unsorted` |
| `MIN_FILE_AGE_SECONDS` | `2` | Wait time after file appears |
| `SUMMARY_HOUR` | `18` | Hour for the automatic daily summary |

To add a new lecture, just create the folder — no code change needed.
The agent scans `~/Studium` at startup and picks up new folders
automatically on the next run (or call `classifier.reload_tree()`).

## 4-week implementation plan

| Week | Goal |
|------|------|
| 1 | Set up watchdog watcher + rule-based classifier. Move files manually. |
| 2 | Integrate LLM classifier. Test with real files. |
| 3 | Add undo/rollback, JSON log, collision handling. |
| 4 | Add daily summary report, CLI polish, README, demo video. |

## Agentic AI concepts demonstrated

- **Perception** — watchdog observes the file system in real time via both
  `on_created` and `on_moved` events
- **Decision-making** — LLM reasons over file contents and the real folder
  tree to choose the best placement
- **Action** — executor moves the file and records intent before acting
- **Self-correction** — low-confidence results are quarantined in `_Unsorted`
  rather than placed incorrectly
- **Memory** — JSON-lines log persists all decisions across restarts
- **Reflection** — daily summary lets the agent review its own actions

## Troubleshooting

**Watcher sees `.tmp` but not the final file**
The final file arrives via a rename, not a new creation. Make sure `on_moved`
is implemented in `watcher.py` — see the `on_moved` section above.

**"Cannot reach Ollama" error**
Run `ollama serve` in a separate terminal before starting the agent.

**File lands in `_Unsorted`**
The LLM confidence was below the threshold. Check that the semester and
lecture folder names in `~/Studium` are descriptive enough for the LLM to
match against. Rename vague folders like `"Mathe"` to `"Mathematik 1"`.

**Wrong lecture chosen**
Increase `MAX_CONTENT_CHARS` in `config.py` to give the LLM more context,
or rename the lecture folder to be more specific.