# Study Buddy Chatbot

This is a small terminal chatbot that keeps a running conversation history, remembers simple user preferences, and refuses requests outside its study support scope.

## Quick start

1. Create the virtual environment:

   ```powershell
   C:/Users/Gui00003/AppData/Local/Programs/Python/Python312/python.exe -m venv .venv
   ```

2. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the project in editable mode:

   ```powershell
   python -m pip install -e .
   ```

4. Start the bot:

   ```powershell
   study-buddy
   ```

5. Put your OpenAI key in [.env](.env). The project ships with a placeholder file so you only need to replace the value for `OPENAI_API_KEY`.

## Config

Edit [config/study_buddy.toml](config/study_buddy.toml) to change the persona, scope, and refusal rules without touching code.

The default model is `gpt-4.1-mini`, which keeps the API cost low while still handling multi-turn study conversations. You can override it in [.env](.env) or the config file.

## Notes

The bot stores lightweight conversation state in [.study_buddy_state.json](.study_buddy_state.json) so it can remember previous turns between runs. Use `/reset` inside the chat to clear it.

## README: Study Buddy Chatbot (Functions & Usage)

This README explains the key functions, how the system is wired, and how to run and test the chatbot.

Core files
- `config/study_buddy.toml`: persona, allowed scope, refusal messages, and LLM defaults.
- `.env`: store `OPENAI_API_KEY` and optional overrides (`OPENAI_MODEL`, `OPENAI_TEMPERATURE`).
- `src/study_buddy/chatbot.py`: main runtime and CLI.

Key functions and classes (in `src/study_buddy/chatbot.py`)
- `load_config(config_path)`: loads TOML configuration.
- `load_state(state_path)`: loads JSON conversation state (memory).
- `build_bot(config_path, state_path)`: returns a `StudyBuddyBot` instance.
- `StudyBuddyBot.chat(user_text)`: main entry point. Checks `/reset`, scope, updates memory, and calls the LLM.
- `StudyBuddyBot._generate_llm_response(user_text, topic)`: builds the system prompt and calls OpenAI.
- `StudyBuddyBot._build_system_prompt(topic)`: composes persona, scope, refusal rules, and memory for the system prompt.
- `StudyBuddyBot._history_messages()`: converts stored turns into LLM messages.
- `StudyBuddyBot._looks_off_topic(normalized)`: refuses out-of-scope requests before contacting the LLM.
- `StudyBuddyBot._extract_topic(text)`: simple heuristics to find a study topic in user text.
- `StudyBuddyBot._extract_memory_fact(text)`: captures facts like subject/goal and stores them.
- `StudyBuddyBot._learn_from_turn(user_text, topic)`: updates `state.profile` and `state.current_topic`.
- `StudyBuddyBot._save_state()`: persists conversation state.

Run the bot (quick start)
1. Activate the venv:

```powershell
.\.venv\Scripts\Activate.ps1
```

2. Install in editable mode (only once or after changes):

```powershell
python -m pip install -e .
```

3. Put your OpenAI API key in `.env` (replace the placeholder value):

```text
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TEMPERATURE=0.4
```

4. Run the bot:

```powershell
study-buddy
```

Programmatic test (offline)
You can test the call flow without real API usage by injecting a fake `client` implementing `chat.completions.create(...)`.

To run:
.\.venv\Scripts\study-buddy.exe

Notes and recommendations
- Keep `.env` out of version control (already in `.gitignore`).
- Tune the system prompt in `StudyBuddyBot._build_system_prompt` or edit `config/study_buddy.toml` to change persona or refusal wording.
- Extend `_extract_memory_fact` to capture more memory fields if desired.

If you want, I can also add a `USAGE.md` or integrate tests to validate refusal and memory behavior automatically.