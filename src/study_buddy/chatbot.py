from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11 fallback
    tomllib = None


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "study_buddy.toml"
DEFAULT_STATE_PATH = ROOT / ".study_buddy_state.json"
DEFAULT_ENV_PATH = ROOT / ".env"
MAX_TURNS = 24

REQUEST_WORDS = {"can you", "could you", "please", "tell me", "write", "make", "give me", "recommend", "show me"}
STUDY_INTENT_WORDS = {
    "study",
    "studying",
    "exam",
    "quiz",
    "flashcard",
    "flashcards",
    "homework",
    "assignment",
    "notes",
    "revise",
    "revision",
    "learn",
    "lesson",
    "lecture",
    "topic",
    "course",
    "class",
    "subject",
    "deadline",
    "plan",
    "summarize",
    "summary",
    "explain",
    "review",
    "help me with",
    "help with",
    "what should i study",
    "what do i study",
    "where do i start",
}

load_dotenv(DEFAULT_ENV_PATH)


@dataclass
class ConversationState:
    turns: list[dict[str, str]] = field(default_factory=list)
    profile: dict[str, str] = field(default_factory=dict)
    current_topic: str = ""


class StudyBuddyBot:
    def __init__(
        self,
        config: dict[str, Any],
        state: ConversationState,
        state_path: Path,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.state_path = state_path
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.client = client or (OpenAI(api_key=self.api_key) if self.api_key else None)
        self.model = os.getenv("OPENAI_MODEL") or self.config.get("llm", {}).get("model", "gpt-4.1-mini")
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE") or self.config.get("llm", {}).get("temperature", 0.4))
        self.debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")

    @property
    def persona(self) -> dict[str, str]:
        return self.config.get("persona", {})

    @property
    def scope(self) -> dict[str, Any]:
        return self.config.get("scope", {})

    @property
    def refusal(self) -> dict[str, str]:
        return self.config.get("refusal", {})

    @property
    def responses(self) -> dict[str, str]:
        return self.config.get("responses", {})

    def chat(self, user_text: str) -> str:
        normalized = self._normalize(user_text)

        if normalized in {"/reset", "reset"}:
            self.state = ConversationState()
            self._save_state()
            return "Conversation reset. What do you want to study next?"

        if self._looks_off_topic(normalized):
            # For off-topic requests return this exact refusal string
            return "I can help with studying, but I need a bit more detail. What topic should we work on?"

        topic = self._extract_topic(user_text) or self.state.current_topic or self._last_subject()
        if topic:
            self.state.current_topic = topic

        self._learn_from_turn(user_text, topic)
        response = self._generate_llm_response(user_text, topic)
        self._append_turn("user", user_text)
        self._append_turn("assistant", response)
        self._trim_history()
        self._save_state()
        return response

    def _generate_llm_response(self, user_text: str, topic: str) -> str:
        if not self.client or not self.api_key:
            return "I need an OpenAI API key in .env before I can answer with the language model. Set OPENAI_API_KEY and try again."

        system_prompt = self._build_system_prompt(topic)
        messages = [{"role": "system", "content": system_prompt}, *self._history_messages(), {"role": "user", "content": user_text}]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
            )
        except Exception as exc:  # capture and optionally print traceback for debugging
            if self.debug:
                import traceback

                traceback.print_exc()
            # For other errors, report the exception message back to the user
            return str(exc)

        # prefer explicit content if present
        try:
            content = response.choices[0].message.content if getattr(response, "choices", None) else ""
        except Exception:
            content = ""

        if not content:
            # report empty-response as an error string back to the user
            try:
                return f"model returned empty content: {response}"
            except Exception:
                return "model returned empty content"
        return content.strip()

    def _build_system_prompt(self, topic: str) -> str:
        persona = self.persona
        scope = self.scope
        refusal = self.refusal
        profile_lines = [f"- {key.replace('_', ' ')}: {value}" for key, value in self.state.profile.items()]
        memory_block = "\n".join(profile_lines) if profile_lines else "- none yet"
        allowed_topics = ", ".join(scope.get("allowed_topics", []))
        return "\n".join(
            [
                f"You are {persona.get('name', 'Study Buddy')}, a study-only assistant.",
                f"Voice: {persona.get('voice', 'calm and practical')}.",
                f"Style: {persona.get('style', 'keep replies concise and helpful')}.",
                f"Behavior: {persona.get('behavior', 'track the current topic and adapt to the learner')}",
                "",
                "Current memory:",
                memory_block,
                "",
                "Scope:",
                f"Only help with: {allowed_topics}.",
                f"If the user asks for something outside that scope, refuse using this idea: {refusal.get('message', 'I can only help with study-related requests.')}.",
                f"Then redirect using: {refusal.get('redirect', 'Please give me a study topic or assignment.')}.",
                "Always keep the conversation coherent across turns, refer back to prior context when useful, and ask at most one follow-up question.",
                f"The current topic is: {topic or self.state.current_topic or self._last_subject() or 'not set yet'}.",
            ]
        )

    def _history_messages(self) -> list[dict[str, str]]:
        messages = []

        for turn in self.state.turns:
            role = turn.get("role")
            content = turn.get("content") or turn.get("text") or ""

            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        return messages
    def _refusal(self, topic: str) -> str:
        message = self.refusal.get("message", "I can only help with study-related requests.")
        redirect = self.refusal.get("redirect", "Please give me a study topic or assignment.")
        allowed = ", ".join(self.scope.get("allowed_topics", []))
        if topic:
            message = message.format(topic=topic)
        return f"{message} {redirect} Allowed areas include: {allowed}."

    def _looks_off_topic(self, normalized: str) -> bool:
        study_intent_words = set(self.scope.get("allowed_keywords", [])) | STUDY_INTENT_WORDS
        if self._contains_any(normalized, study_intent_words):
            return False
        if self._contains_any(normalized, self.scope.get("off_topic_keywords", [])):
            return True
        return self._contains_any(normalized, REQUEST_WORDS)

    def _off_topic_focus(self, normalized: str) -> str:
        for keyword in self.scope.get("off_topic_keywords", []):
            if keyword in normalized:
                return keyword
        return "that request"

    def _contains_any(self, text: str, phrases: list[str] | set[str]) -> bool:
        return any(phrase in text for phrase in phrases)

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower().strip())

    def _extract_topic(self, text: str) -> str:
        patterns = [
            r"(?:about|on|for|with)\s+(.+)$",
            r"(?:help me with|help with|study|learn|revise|review|quiz me on|explain)\s+(.+)$",
            r"(?:my subject is|i am studying|i'm studying)\s+(.+)$",
        ]
        stripped = text.strip(" .!?\n\t")
        for pattern in patterns:
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .!?\n\t")
                if candidate:
                    return candidate
        return ""

    def _extract_memory_fact(self, text: str) -> tuple[str, str] | None:
        patterns = [
            (r"(?:my subject is|i am studying|i'm studying)\s+(.+)$", "subject"),
            (r"(?:my exam is|my test is|my deadline is)\s+(.+)$", "deadline"),
            (r"(?:i prefer|i like)\s+(.+)$", "preference"),
            (r"(?:my goal is|i want to)\s+(.+)$", "goal"),
        ]
        for pattern, key in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .!?\n\t")
                if value:
                    return key, value
        return None

    def _learn_from_turn(self, user_text: str, topic: str) -> None:
        fact = self._extract_memory_fact(user_text)
        if fact:
            key, value = fact
            self.state.profile[key] = value
        elif topic and not self.state.current_topic:
            self.state.current_topic = topic

    def _last_subject(self) -> str:
        return self.state.profile.get("subject", "") or self.state.current_topic

    def _append_turn(self, role: str, text: str) -> None:
        self.state.turns.append({"role": role, "content": text})

    def _trim_history(self) -> None:
        if len(self.state.turns) > MAX_TURNS:
            self.state.turns = self.state.turns[-MAX_TURNS:]

    def _save_state(self) -> None:
        data = {
            "turns": self.state.turns,
            "profile": self.state.profile,
            "current_topic": self.state.current_topic,
        }
        self.state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config(config_path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("Python 3.12 or newer is required to read the TOML config.")
    return tomllib.loads(config_path.read_text(encoding="utf-8"))


def load_state(state_path: Path) -> ConversationState:
    if not state_path.exists():
        return ConversationState()
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    return ConversationState(
        turns=list(raw.get("turns", [])),
        profile=dict(raw.get("profile", {})),
        current_topic=str(raw.get("current_topic", "")),
    )


def build_bot(config_path: Path, state_path: Path) -> StudyBuddyBot:
    config = load_config(config_path)
    state = load_state(state_path)
    return StudyBuddyBot(config=config, state=state, state_path=state_path)


def run_chat(bot: StudyBuddyBot) -> None:
    title = bot.persona.get("name", "Study Buddy")
    print(f"{title} ready. Type /reset to clear memory and /exit to quit.\n")
    print(bot.responses.get("greeting", "I am here to help you study."))
    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        if not user_text:
            continue
        if user_text.lower() in {"/exit", "exit", "quit"}:
            print("Goodbye.")
            return

        reply = bot.chat(user_text)
        print(f"{title}: {reply}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the study buddy chatbot.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to the TOML config file.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="Path to the JSON memory file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    bot = build_bot(args.config, args.state)
    run_chat(bot)


if __name__ == "__main__":
    main(sys.argv[1:])