import json
import os

from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = """You are ThreadMind, a helpful and friendly AI assistant that remembers the people it talks to.
Use what you know about the user naturally, without announcing that you remember it.
Format answers in Markdown when it helps readability (lists, code blocks, tables)."""

MEMORY_PROMPT = """You maintain long-term memory about a user for an AI assistant.
Read the latest exchange and extract NEW durable facts about the user worth remembering in future conversations:
their name, preferences, goals, projects, background, recurring constraints.
Ignore small talk, one-off questions, and anything already covered by the known facts.
Each fact is a short third-person sentence, e.g. "User's name is Asha." or "User prefers Python over Java."

Known facts:
{known}

Latest exchange:
User: {user}
Assistant: {assistant}

Return a JSON array of strings (empty if nothing new)."""

NO_AFC = types.AutomaticFunctionCallingConfig(disable=True)

TITLE_PROMPT = """Write a short title (max 6 words, no quotes, no trailing punctuation) for a chat that starts with:
{message}"""


class GeminiLLM:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client = genai.Client(api_key=self.api_key) if self.api_key else None

    @property
    def configured(self):
        return self._client is not None

    def _require_client(self):
        if not self._client:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to backend/.env and restart the server.")
        return self._client

    async def stream_reply(self, history, memories):
        """Yield text chunks for the reply to `history` (list of {role, content})."""
        client = self._require_client()
        system = SYSTEM_PROMPT
        if memories:
            system += "\n\nWhat you know about the user:\n" + "\n".join(f"- {m}" for m in memories)

        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in history
        ]
        stream = await client.aio.models.generate_content_stream(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system, automatic_function_calling=NO_AFC),
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def generate_title(self, message):
        client = self._require_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=TITLE_PROMPT.format(message=message[:1000]),
            config=types.GenerateContentConfig(automatic_function_calling=NO_AFC),
        )
        return (response.text or "").strip().strip('"').strip()

    async def extract_memories(self, known, user_message, assistant_message):
        client = self._require_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=MEMORY_PROMPT.format(
                known="\n".join(f"- {k}" for k in known) or "(none)",
                user=user_message,
                assistant=assistant_message,
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", automatic_function_calling=NO_AFC
            ),
        )
        facts = json.loads(response.text or "[]")
        return [f.strip() for f in facts if isinstance(f, str) and f.strip()]
