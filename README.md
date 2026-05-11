# Smart File Organizer Agent

An agentic AI system that watches a folder and automatically classifies
and sorts files using a two-stage pipeline: fast rule-based heuristics
first, then an LLM call only when the extension is ambiguous.

## Project structure

```
file_organizer_agent/
├── main.py               # entry point + CLI
├── config.py             # all categories, rules, and settings
├── requirements.txt
├── .env.example          # copy to .env
├── agent/
│   ├── classifier.py     # two-stage classifier (rules + LLM)
│   ├── executor.py       # file mover + undo stack + log writer
│   └── watcher.py        # watchdog event handler
├── utils/
│   └── reporter.py       # daily summary report
└── tests/
    └── test_classifier.py  # unit tests (no API key needed)
```

## Setup

```bash
# 1. Clone / download the project
cd file_organizer_agent

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
cp .env.example .env
# Edit .env and add your OpenAI API key

# 5. Run the tests (no API key needed)
python -m pytest tests/ -v
```

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

1. **watchdog** detects a new file in the watched folder.
2. A short sleep waits for the file to finish writing.
3. **Rule-based classifier** checks the extension against a lookup table.
   - Known extension (e.g. `.jpg`) → category assigned instantly, no API call.
   - Ambiguous extension (e.g. `.pdf`, `.py`, `.md`) → goes to stage 2.
4. **LLM classifier** sends the filename to GPT-4o-mini and gets back:
   - `category` (one of 11 folders)
   - `confidence` (0–1)
   - `reason` (short explanation)
5. **Executor** moves the file to the appropriate sub-folder and writes
   a JSON-lines log entry.
6. **Undo stack** lets you roll back the last move (or all moves) in a session.
7. **Daily summary** is printed at 6pm and on shutdown.

## Configuration

Edit `config.py` to:
- Add or rename category folders (`CATEGORY_FOLDERS`)
- Add extension rules (`EXTENSION_MAP`)
- Change the LLM confidence threshold (`CONFIDENCE_THRESHOLD`)
- Change the daily summary time (`SUMMARY_HOUR`)

## 4-week implementation plan

| Week | Goal |
|------|------|
| 1 | Set up watchdog watcher + rule-based classifier. Move files manually. |
| 2 | Integrate LLM classifier. Test with real files. |
| 3 | Add undo/rollback, JSON log, collision handling. |
| 4 | Add daily summary report, CLI polish, README, demo video. |

## Agentic AI concepts demonstrated

- **Perception** — watchdog monitors the file system for events
- **Decision-making** — two-stage classifier chooses a category
- **Action** — executor moves files and writes logs
- **Self-correction** — low-confidence results fall back to "misc"
- **Memory** — JSON log persists all decisions across sessions
- **Reflection** — daily summary lets the agent "review" its work

## Estimated API cost

Using GPT-4o-mini (~$0.15 / 1M tokens):
- Each LLM call uses ~100–150 tokens
- 100 ambiguous files/day ≈ $0.002/day
- Well within free-tier credits for a university project
