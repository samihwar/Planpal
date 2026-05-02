"""
Task parser with pluggable LLM backends.
Currently uses Ollama locally, ready to scale to cloud LLMs.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Mapping
import json
import logging
import re

logger = logging.getLogger(__name__)    # for debugging and error logging

DEFAULT_USER_PROFILE = {
    "timezone": "UTC",
    "time_phrase_defaults": {},
    "followup_preference": "ask_when_ambiguous",
    "duration_policy": "never_assume",
}


def normalize_user_profile(profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
    normalized = {
        "timezone": DEFAULT_USER_PROFILE["timezone"],
        "time_phrase_defaults": {},
        "followup_preference": DEFAULT_USER_PROFILE["followup_preference"],
        "duration_policy": DEFAULT_USER_PROFILE["duration_policy"],
    }
    if profile is None:
        return normalized

    timezone_value = profile.get("timezone")
    if isinstance(timezone_value, str) and timezone_value.strip():
        normalized["timezone"] = timezone_value.strip()

    time_phrase_defaults = profile.get("time_phrase_defaults")
    if isinstance(time_phrase_defaults, Mapping):
        normalized["time_phrase_defaults"] = {
            str(key).strip().lower(): str(value).strip()
            for key, value in time_phrase_defaults.items()
            if str(key).strip() and str(value).strip()
        }

    followup_preference = profile.get("followup_preference")
    if isinstance(followup_preference, str) and followup_preference.strip():
        normalized["followup_preference"] = followup_preference.strip()

    duration_policy = profile.get("duration_policy")
    if isinstance(duration_policy, str) and duration_policy.strip():
        normalized["duration_policy"] = duration_policy.strip()

    return normalized

NUMERIC_DATE_PATTERNS = (
    re.compile(r"\b(?P<year>\d{4})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})\b"),
    re.compile(r"\b(?P<day>\d{1,2})[./-](?P<month>\d{1,2})[./-](?P<year>\d{4})\b"),
)
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
RELATIVE_WEEKDAY_PATTERN = re.compile(
    r"\b(?P<modifier>this|next)\s+(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
TWENTY_FOUR_HOUR_TIME_PATTERN = re.compile(r"\b(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b")
AM_PM_TIME_PATTERN = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?\s*(?P<meridiem>am|pm)\b",
    re.IGNORECASE,
)
AT_HOUR_TIME_PATTERN = re.compile(
    r"\bat\s+(?P<hour>1?\d|2[0-3])(?::(?P<minute>[0-5]\d))?\b(?!\s*(?:hour|hours|hr|hrs)\b)",
    re.IGNORECASE,
)


class TaskParserBackend(ABC):
    """Abstract base class for task parsing backends."""
    
    @abstractmethod
    def parse(self, text: str) -> Dict:
        """
        Parse natural language task into structured format.
        
        Args:
            text: Natural language task description
            
        Returns:
            dict with keys:
                - title (str): short summary
                - description (str): full description
                - date (str | None): task date as YYYY-MM-DD
                - time (str | None): task time as HH:MM in 24-hour format
                - duration (float | None): hours as number
                
        Raises:
            RuntimeError: If LLM service fails
            ValueError: If output is invalid
        """
        pass

    @abstractmethod
    def resolve_temporal_update(self, task: Dict, answer: str) -> Dict:
        """
        Resolve a date/time follow-up using the current task as context.

        Returns:
            dict with keys:
                - date (str | None)
                - time (str | None)
        """
        pass

    @abstractmethod
    def revise_parse(self, text: str, current_parse: Dict) -> Dict:
        """
        Fill unresolved fields from saved preferences before asking follow-up questions.

        Returns:
            dict with keys:
                - title (str)
                - description (str)
                - date (str | None)
                - time (str | None)
                - duration (float | None)
        """
        pass
    
    def _validate_output(self, parsed: Dict) -> None:
        """Validate parsed output has required fields."""
        required_fields = {"title", "description", "date", "time", "duration", "date_evidence"}
        keys = set(parsed.keys())
        missing = required_fields - keys
        unexpected = keys - required_fields
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        if unexpected:
            raise ValueError(f"Unexpected fields: {unexpected}")
        
        # Type validation
        if not isinstance(parsed["title"], str):
            raise ValueError("title must be a string")
        if not isinstance(parsed["description"], str):
            raise ValueError("description must be a string")
        if parsed["date"] is not None and not isinstance(parsed["date"], str):
            raise ValueError("date must be a YYYY-MM-DD string or null")
        if parsed["time"] is not None and not isinstance(parsed["time"], str):
            raise ValueError("time must be an HH:MM string or null")
        if parsed["duration"] is not None and not isinstance(parsed["duration"], (int, float)):
            raise ValueError("duration must be a number or null")
        if parsed["date_evidence"] is not None and not isinstance(parsed["date_evidence"], str):
            raise ValueError("date_evidence must be a string or null")

    def _validate_temporal_output(self, parsed: Dict) -> None:
        """Validate temporal follow-up output."""
        required_fields = {"date", "time"}
        keys = set(parsed.keys())
        missing = required_fields - keys
        unexpected = keys - required_fields
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        if unexpected:
            raise ValueError(f"Unexpected fields: {unexpected}")

        if parsed["date"] is not None and not isinstance(parsed["date"], str):
            raise ValueError("date must be a YYYY-MM-DD string or null")
        if parsed["time"] is not None and not isinstance(parsed["time"], str):
            raise ValueError("time must be an HH:MM string or null")

    def _validate_midnight_check_output(self, parsed: Dict) -> None:
        """Validate midnight check output."""
        required_fields = {"keep_midnight_time"}
        keys = set(parsed.keys())
        missing = required_fields - keys
        unexpected = keys - required_fields
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        if unexpected:
            raise ValueError(f"Unexpected fields: {unexpected}")
        if not isinstance(parsed["keep_midnight_time"], bool):
            raise ValueError("keep_midnight_time must be a boolean")

    def _build_profile_context(self) -> str:
        profile_json = json.dumps(self.user_profile, ensure_ascii=True, sort_keys=True)
        adaptive_rules = list(self.adaptive_rules) or [
            "Fill only fields that are resolved by the optional user profile. Keep everything else null."
        ]
        adaptive_rules_text = "\n".join(f"- {rule}" for rule in adaptive_rules)
        return (
            f"User profile JSON:\n{profile_json}\n\n"
            f"Adaptive parsing rules:\n{adaptive_rules_text}\n"
        )

    def _apply_date_consistency_overrides(
        self,
        parsed: Dict,
        source_text: str,
        reference_now: datetime,
    ) -> Dict:
        explicit_date = self._resolve_explicit_date_from_text(source_text, reference_now)
        if explicit_date is None:
            return parsed

        updated = dict(parsed)
        updated["date"] = explicit_date
        return updated

    def _apply_time_consistency_overrides(
        self,
        parsed: Dict,
        source_text: str,
        reference_now: datetime,
        use_profile_defaults: bool = False,
    ) -> Dict:
        explicit_time = self._resolve_explicit_time_from_text(source_text)
        updated = dict(parsed)

        if explicit_time is not None:
            if explicit_time.get("resolved_time") is not None:
                updated["time"] = explicit_time["resolved_time"]
                return self._roll_unanchored_past_time_forward(updated, reference_now)

            candidate_time = updated.get("time")
            candidate_hour = self._extract_hour_from_time(candidate_time)
            if candidate_hour is None:
                return updated

            explicit_hour = explicit_time.get("hour")
            if explicit_hour is not None and candidate_hour in {
                explicit_hour,
                explicit_hour % 12,
                (explicit_hour % 12) + 12,
            }:
                return self._roll_unanchored_past_time_forward(updated, reference_now)

            updated["time"] = None
            return updated

        if use_profile_defaults:
            profile_default_time = self._resolve_profile_time_default(source_text)
            if profile_default_time is not None:
                if updated.get("time") is None:
                    updated["time"] = profile_default_time
                return self._roll_unanchored_past_time_forward(updated, reference_now)

        return self._roll_unanchored_past_time_forward(updated, reference_now)

    def _roll_unanchored_past_time_forward(self, parsed: Dict, reference_now: datetime) -> Dict:
        if parsed.get("date_explicit") is not False:
            return parsed

        parsed_date = parsed.get("date")
        parsed_time = parsed.get("time")
        if not isinstance(parsed_date, str) or not isinstance(parsed_time, str):
            return parsed

        try:
            scheduled_at = datetime.fromisoformat(f"{parsed_date}T{parsed_time}")
        except ValueError:
            return parsed

        if scheduled_at > reference_now:
            return parsed

        updated = dict(parsed)
        while scheduled_at <= reference_now:
            scheduled_at += timedelta(days=1)
        updated["date"] = scheduled_at.date().isoformat()
        return updated

    def _strip_internal_fields(self, parsed: Dict) -> Dict:
        public_parse = dict(parsed)
        public_parse.pop("date_explicit", None)
        public_parse.pop("date_evidence", None)
        return public_parse

    def _normalize_date_explicit_flag(
        self,
        parsed: Dict,
        source_text: str,
        current_parse: Mapping[str, Any] | None = None,
    ) -> Dict:
        updated = dict(parsed)
        evidence = updated.get("date_evidence")
        has_source_evidence = (
            isinstance(evidence, str)
            and bool(evidence.strip())
            and evidence.casefold() in source_text.casefold()
        )
        updated["date_explicit"] = (
            updated.get("date") is not None
            and has_source_evidence
            and not (current_parse is not None and current_parse.get("date") is None)
        )
        return updated

    def _resolve_explicit_date_from_text(
        self,
        text: str,
        reference_now: datetime,
    ) -> str | None:
        numeric_date = self._resolve_numeric_date(text)
        if numeric_date is not None:
            return numeric_date

        weekday_date = self._resolve_relative_weekday(text, reference_now)
        if weekday_date is not None:
            return weekday_date

        return None

    def _resolve_numeric_date(self, text: str) -> str | None:
        for pattern in NUMERIC_DATE_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            try:
                resolved = datetime(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                )
            except ValueError:
                continue
            return resolved.date().isoformat()
        return None

    def _resolve_relative_weekday(self, text: str, reference_now: datetime) -> str | None:
        match = RELATIVE_WEEKDAY_PATTERN.search(text)
        if match is None:
            return None

        weekday_name = match.group("weekday").lower()
        target_weekday = WEEKDAY_INDEX[weekday_name]
        current_weekday = reference_now.weekday()
        days_until = (target_weekday - current_weekday) % 7

        modifier = match.group("modifier").lower()
        if modifier == "next" and days_until == 0:
            days_until = 7

        resolved = reference_now.date() + timedelta(days=days_until)
        return resolved.isoformat()

    def _resolve_explicit_time_from_text(self, text: str) -> Dict[str, Any] | None:
        match = TWENTY_FOUR_HOUR_TIME_PATTERN.search(text)
        if match is not None:
            return {
                "resolved_time": f"{int(match.group('hour')):02d}:{int(match.group('minute')):02d}",
            }

        match = AM_PM_TIME_PATTERN.search(text)
        if match is not None:
            hour = int(match.group("hour"))
            minute = int(match.group("minute") or 0)
            meridiem = match.group("meridiem").lower()
            if meridiem == "am":
                hour = 0 if hour == 12 else hour
            else:
                hour = 12 if hour == 12 else hour + 12
            return {"resolved_time": f"{hour:02d}:{minute:02d}"}

        match = AT_HOUR_TIME_PATTERN.search(text)
        if match is not None:
            return {
                "resolved_time": None,
                "hour": int(match.group("hour")),
            }

        return None

    def _resolve_profile_time_default(self, text: str) -> str | None:
        lowered_text = text.casefold()
        for phrase, default_time in self.user_profile.get("time_phrase_defaults", {}).items():
            if phrase and phrase.casefold() in lowered_text:
                return default_time
        return None

    def _extract_hour_from_time(self, time_value: Any) -> int | None:
        if not isinstance(time_value, str) or ":" not in time_value:
            return None
        hour_text, _ = time_value.split(":", 1)
        try:
            return int(hour_text)
        except ValueError:
            return None


class OllamaBackend(TaskParserBackend):
    """Ollama-based task parser for local development."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        temperature: float = 0,
        request_timeout: float | tuple[float, float] = (5, 120),
        user_profile: Mapping[str, Any] | None = None,
        adaptive_rules: Iterable[str] | None = None,
    ):
        """
        Initialize Ollama backend.
        
        Args:
            base_url: Ollama API endpoint
            model: Model name (llama3, mistral, etc.)
            temperature: Sampling temperature. Lower values are more deterministic.
            request_timeout: Requests timeout. Tuple means (connect_timeout, read_timeout).
            user_profile: Optional parsing preferences.
            adaptive_rules: Optional parsing rules.
        """
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.request_timeout = request_timeout
        self.user_profile = normalize_user_profile(user_profile)
        self.adaptive_rules = list(adaptive_rules or [])
        logger.info(f"Initialized Ollama backend: {base_url} with model {model}")
    
    def parse(self, text: str) -> Dict:
        import requests
        
        current_local_datetime = datetime.now()
        
        prompt = self._build_prompt(text, current_local_datetime.strftime("%Y-%m-%d %H:%M"))
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self.temperature},
                },
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            output = response.json()["response"]
            parsed = json.loads(output)
            
            self._validate_output(parsed)
            parsed = self._normalize_date_explicit_flag(parsed, text)
            parsed = self._apply_date_consistency_overrides(parsed, text, current_local_datetime)
            parsed = self._apply_time_consistency_overrides(parsed, text, current_local_datetime)
            parsed = self._clear_unconfirmed_midnight(parsed, text)
            parsed = self._strip_internal_fields(parsed)
            logger.debug(f"Successfully parsed task: {parsed['title']}")
            return parsed
            
        except (requests.Timeout, TimeoutError):
            logger.error("Ollama request timed out")
            raise RuntimeError("Task parsing timed out. Ollama may be stopped, starting up, or overloaded.")
        except requests.ConnectionError:
            logger.error("Cannot connect to Ollama")
            raise RuntimeError("Cannot connect to Ollama. Is it running?")
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            raise RuntimeError(f"Ollama API request failed: {e}") from e
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Ollama response: {output}")
            raise ValueError(f"Invalid response from Ollama: {e}") from e

    def resolve_temporal_update(self, task: Dict, answer: str) -> Dict:
        import requests

        current_local_datetime = datetime.now()
        prompt = self._build_temporal_update_prompt(task, answer, current_local_datetime.strftime("%Y-%m-%d %H:%M"))

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self.temperature},
                },
                timeout=self.request_timeout
            )
            response.raise_for_status()

            output = response.json()["response"]
            parsed = json.loads(output)

            self._validate_temporal_output(parsed)
            parsed = self._apply_date_consistency_overrides(parsed, answer, current_local_datetime)
            parsed = self._apply_time_consistency_overrides(
                parsed,
                answer,
                current_local_datetime,
                use_profile_defaults=True,
            )
            parsed = self._clear_unconfirmed_midnight(parsed, answer)
            return parsed

        except (requests.Timeout, TimeoutError):
            logger.error("Ollama temporal follow-up request timed out")
            raise RuntimeError("Temporal follow-up parsing timed out. Ollama may be stopped, starting up, or overloaded.")
        except requests.ConnectionError:
            logger.error("Cannot connect to Ollama")
            raise RuntimeError("Cannot connect to Ollama. Is it running?")
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            raise RuntimeError(f"Ollama API request failed: {e}") from e
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Ollama temporal follow-up response: {output}")
            raise ValueError(f"Invalid temporal follow-up response from Ollama: {e}") from e

    def revise_parse(self, text: str, current_parse: Dict) -> Dict:
        import requests

        current_local_datetime = datetime.now()
        prompt = self._build_revision_prompt(text, current_parse, current_local_datetime.strftime("%Y-%m-%d %H:%M"))

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self.temperature},
                },
                timeout=self.request_timeout
            )
            response.raise_for_status()

            output = response.json()["response"]
            parsed = json.loads(output)

            self._validate_output(parsed)
            parsed = self._normalize_date_explicit_flag(parsed, text, current_parse=current_parse)
            parsed = self._apply_date_consistency_overrides(parsed, text, current_local_datetime)
            parsed = self._apply_time_consistency_overrides(
                parsed,
                text,
                current_local_datetime,
                use_profile_defaults=True,
            )
            parsed = self._clear_unconfirmed_midnight(parsed, text)
            parsed = self._strip_internal_fields(parsed)
            return parsed

        except (requests.Timeout, TimeoutError):
            logger.error("Ollama revision request timed out")
            raise RuntimeError("Task revision timed out. Ollama may be stopped, starting up, or overloaded.")
        except requests.ConnectionError:
            logger.error("Cannot connect to Ollama")
            raise RuntimeError("Cannot connect to Ollama. Is it running?")
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            raise RuntimeError(f"Ollama API request failed: {e}") from e
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Ollama revision response: {output}")
            raise ValueError(f"Invalid revision response from Ollama: {e}") from e
    
    def _build_prompt(self, text: str, current_local_datetime: str) -> str:
        """Build the parsing prompt."""
        return f"""You are a task parser. The current local datetime is {current_local_datetime}.

Convert the following into a JSON object with these exact fields:
- title: short title (max 50 characters)
- description: full description of the task
- date: date only in YYYY-MM-DD format
- time: time only in 24-hour HH:MM format
- duration: hours as a number (e.g., 2.5 for 2.5 hours)
- date_evidence: the exact date/date-phrase text copied from the input, or null if the input has no explicit date phrase

Rules:
- The input may be written in any language and may use casual day-to-day phrasing
- Preserve the user's language in the title and description
- Convert any date expression you can confidently understand into the date field
- Convert any time expression you can confidently understand into the time field using 24-hour HH:MM
- date_evidence must be copied exactly from the input text and must not be a time or duration phrase
- If a time is given without an explicit date, schedule the *next* future occurrence of that time relative to the current local datetime
- If the user explicitly gives a date, preserve that date even when the resulting datetime is in the past
- If the user gives only a date or day reference and no time, set time to null
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Never infer a time from the type of activity alone
- Keep title and description always filled based on the sentence, even if other details are missing
- If the date is missing or cannot be inferred, use null
- If the time is missing or cannot be inferred, use null
- If the duration is missing or cannot be inferred, use null
- Return exactly the six keys listed above
- Return only valid JSON and never include markdown or explanations

Input: "{text}"

Output only valid JSON, no explanation or markdown formatting."""

    def _build_temporal_update_prompt(self, task: Dict, answer: str, current_local_datetime: str) -> str:
        """Build the temporal follow-up prompt."""
        task_json = json.dumps(task, ensure_ascii=True)
        profile_context = self._build_profile_context()
        return f"""You resolve missing scheduling details for a task. The current local datetime is {current_local_datetime}.

{profile_context}

Existing task JSON:
{task_json}

User clarification:
"{answer}"

Return a JSON object with these exact fields:
- date: final date in YYYY-MM-DD format or null
- time: final time in 24-hour HH:MM format or null

Rules:
- The clarification may be written in any language and may be informal
- Use the existing task and the clarification together
- Preserve an existing date or time when the clarification does not change it
- If the clarification adds both date and time, return both updated values
- Treat informal temporal language as valid input when the meaning is clear from context
- This includes abbreviations, slang, transliterations, shorthand, and small typos in any language
- If an informal date or time phrase is clear enough to a human reader, treat it as explicit rather than missing
- Use user_profile.time_phrase_defaults only when the clarification includes a matching phrase
- If the clarification does not resolve a missing field explicitly, keep it null
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Do not guess missing fields
- Return exactly the keys date and time
- Return only valid JSON, with no explanation and no markdown
"""

    def _build_revision_prompt(self, text: str, current_parse: Dict, current_local_datetime: str) -> str:
        """Build the preference-fill prompt used before asking follow-up questions."""
        current_parse_json = json.dumps(current_parse, ensure_ascii=True)
        profile_context = self._build_profile_context()
        return f"""You fill missing task scheduling fields from saved user preferences. The current local datetime is {current_local_datetime}.

{profile_context}

Original user text:
"{text}"

First-pass JSON:
{current_parse_json}

Return a JSON object with these exact fields:
- title
- description
- date
- time
- duration
- date_evidence

Rules:
- This is stage 2. Stage 1 already parsed only information explicit in the user text.
- Preserve every non-null field from the first-pass JSON.
- Fill only fields that are null in the first-pass JSON.
- date_evidence must be copied exactly from the original user text and must not be a time or duration phrase. Use null if there is no explicit date phrase.
- Use the optional user profile and additional parsing rules as the only source for filling null fields.
- Use user_profile.time_phrase_defaults only when the original user text includes a matching phrase.
- Do not reinterpret the original text to recover new information that is not backed by the profile.
- Do not infer a time from the type of activity alone.
- Do not invent default times, dates, or durations.
- If the profile does not clearly resolve a null field, keep it null.
- Return exactly the six keys and only valid JSON
"""

    def _clear_unconfirmed_midnight(self, parsed: Dict, source_text: str) -> Dict:
        """Clear 00:00 unless the user explicitly asked for midnight."""
        if parsed.get("time") != "00:00":
            return parsed
        if self._should_keep_midnight_time(source_text):
            return parsed
        updated = dict(parsed)
        updated["time"] = None
        return updated

    def _should_keep_midnight_time(self, source_text: str) -> bool:
        import requests

        current_local_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = self._build_midnight_check_prompt(source_text, current_local_datetime)

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self.temperature},
                },
                timeout=self.request_timeout
            )
            response.raise_for_status()

            output = response.json()["response"]
            parsed = json.loads(output)
            self._validate_midnight_check_output(parsed)
            return parsed["keep_midnight_time"]

        except Exception as e:
            logger.warning(f"Midnight confirmation check failed, clearing time defensively: {e}")
            return False

    def _build_midnight_check_prompt(self, source_text: str, current_local_datetime: str) -> str:
        """Build the midnight confirmation prompt."""
        return f"""You decide whether a user's text explicitly asks for midnight. The current local datetime is {current_local_datetime}.

User text:
"{source_text}"

Return a JSON object with this exact field:
- keep_midnight_time: true if the user explicitly asked for midnight or 00:00, otherwise false

Rules:
- The text may be written in any language
- Return true only when midnight is explicitly requested
- If the text only mentions a date or day such as tomorrow, return false
- Return only valid JSON
"""


class OpenAIBackend(TaskParserBackend):
    """OpenAI-based task parser for production scale."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0,
        user_profile: Mapping[str, Any] | None = None,
        adaptive_rules: Iterable[str] | None = None,
    ):
        """
        Initialize OpenAI backend.
        
        Args:
            api_key: OpenAI API key
            model: Model name (gpt-4o-mini, gpt-4o, etc.)
            temperature: Sampling temperature. Lower values are more deterministic.
            user_profile: Optional parsing preferences.
            adaptive_rules: Optional parsing rules.
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.user_profile = normalize_user_profile(user_profile)
        self.adaptive_rules = list(adaptive_rules or [])
        logger.info(f"Initialized OpenAI backend with model {model}")
    
    def parse(self, text: str) -> Dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")
        
        client = OpenAI(api_key=self.api_key)
        current_local_datetime = datetime.now()
        
        prompt = self._build_prompt(text, current_local_datetime.strftime("%Y-%m-%d %H:%M"))
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                timeout=30
            )
            
            parsed = json.loads(response.choices[0].message.content)
            self._validate_output(parsed)
            parsed = self._normalize_date_explicit_flag(parsed, text)
            parsed = self._apply_date_consistency_overrides(parsed, text, current_local_datetime)
            parsed = self._apply_time_consistency_overrides(parsed, text, current_local_datetime)
            parsed = self._clear_unconfirmed_midnight(parsed, text)
            parsed = self._strip_internal_fields(parsed)
            logger.debug(f"Successfully parsed task: {parsed['title']}")
            return parsed
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI API request failed: {e}") from e

    def resolve_temporal_update(self, task: Dict, answer: str) -> Dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        client = OpenAI(api_key=self.api_key)
        current_local_datetime = datetime.now()
        prompt = self._build_temporal_update_prompt(task, answer, current_local_datetime.strftime("%Y-%m-%d %H:%M"))

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                timeout=30
            )

            parsed = json.loads(response.choices[0].message.content)
            self._validate_temporal_output(parsed)
            parsed = self._apply_date_consistency_overrides(parsed, answer, current_local_datetime)
            parsed = self._apply_time_consistency_overrides(
                parsed,
                answer,
                current_local_datetime,
                use_profile_defaults=True,
            )
            parsed = self._clear_unconfirmed_midnight(parsed, answer)
            return parsed

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI API request failed: {e}") from e

    def revise_parse(self, text: str, current_parse: Dict) -> Dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        client = OpenAI(api_key=self.api_key)
        current_local_datetime = datetime.now()
        prompt = self._build_revision_prompt(text, current_parse, current_local_datetime.strftime("%Y-%m-%d %H:%M"))

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                timeout=30
            )

            parsed = json.loads(response.choices[0].message.content)
            self._validate_output(parsed)
            parsed = self._normalize_date_explicit_flag(parsed, text, current_parse=current_parse)
            parsed = self._apply_date_consistency_overrides(parsed, text, current_local_datetime)
            parsed = self._apply_time_consistency_overrides(
                parsed,
                text,
                current_local_datetime,
                use_profile_defaults=True,
            )
            parsed = self._clear_unconfirmed_midnight(parsed, text)
            parsed = self._strip_internal_fields(parsed)
            return parsed

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI API request failed: {e}") from e
    
    def _build_prompt(self, text: str, current_local_datetime: str) -> str:
        """Build the parsing prompt."""
        return f"""You are a task parser. The current local datetime is {current_local_datetime}.

Convert the following into a JSON object with these exact fields:
- title: short summary
- description: full description
- date: date only in YYYY-MM-DD format
- time: time only in 24-hour HH:MM format
- duration: hours as a number or null
- date_evidence: the exact date/date-phrase text copied from the input, or null if the input has no explicit date phrase

Rules:
- The input may be written in any language
- Preserve the user's language in the title and description
- Convert any date expression you can confidently understand into the date field
- Convert any time expression you can confidently understand into the time field using 24-hour HH:MM
- date_evidence must be copied exactly from the input text and must not be a time or duration phrase
- If a time is given without an explicit date, schedule the next future occurrence of that time relative to the current local datetime
- If the user explicitly gives a date, preserve that date even when the resulting datetime is in the past
- If the user gives only a date or day reference and no time, set time to null
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Never infer a time from the type of activity alone
- Keep title and description always filled
- Use null if the date is missing or cannot be inferred
- Use null if the time is missing or cannot be inferred
- Use null if the duration is missing or cannot be inferred
- Return exactly the six keys listed above

Input: "{text}"

Output only valid JSON."""

    def _build_temporal_update_prompt(self, task: Dict, answer: str, current_local_datetime: str) -> str:
        """Build the temporal follow-up prompt."""
        task_json = json.dumps(task, ensure_ascii=True)
        profile_context = self._build_profile_context()
        return f"""You resolve missing scheduling details for a task. The current local datetime is {current_local_datetime}.

{profile_context}

Existing task JSON:
{task_json}

User clarification:
"{answer}"

Return a JSON object with these exact fields:
- date: final date in YYYY-MM-DD format or null
- time: final time in 24-hour HH:MM format or null

Rules:
- The clarification may be written in any language and may be informal
- Use the existing task and the clarification together
- Preserve an existing date or time when the clarification does not change it
- If the clarification adds both date and time, return both updated values
- Treat informal temporal language as valid input when the meaning is clear from context
- This includes abbreviations, slang, transliterations, shorthand, and small typos in any language
- If an informal date or time phrase is clear enough to a human reader, treat it as explicit rather than missing
- Use user_profile.time_phrase_defaults only when the clarification includes a matching phrase
- If the clarification does not resolve a missing field explicitly, keep it null
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Do not guess missing fields
- Return exactly the keys date and time
- Return only valid JSON
"""

    def _build_revision_prompt(self, text: str, current_parse: Dict, current_local_datetime: str) -> str:
        """Build the preference-fill prompt used before asking follow-up questions."""
        current_parse_json = json.dumps(current_parse, ensure_ascii=True)
        profile_context = self._build_profile_context()
        return f"""You fill missing task scheduling fields from saved user preferences. The current local datetime is {current_local_datetime}.

{profile_context}

Original user text:
"{text}"

First-pass JSON:
{current_parse_json}

Return a JSON object with these exact fields:
- title
- description
- date
- time
- duration
- date_evidence

Rules:
- This is stage 2. Stage 1 already parsed only information explicit in the user text.
- Preserve every non-null field from the first-pass JSON.
- Fill only fields that are null in the first-pass JSON.
- date_evidence must be copied exactly from the original user text and must not be a time or duration phrase. Use null if there is no explicit date phrase.
- Use the optional user profile and additional parsing rules as the only source for filling null fields.
- Use user_profile.time_phrase_defaults only when the original user text includes a matching phrase.
- Do not reinterpret the original text to recover new information that is not backed by the profile.
- Do not infer a time from the type of activity alone.
- Do not invent default times, dates, or durations.
- If the profile does not clearly resolve a null field, keep it null.
- Return exactly the six keys and only valid JSON
"""

    def _clear_unconfirmed_midnight(self, parsed: Dict, source_text: str) -> Dict:
        """Clear 00:00 unless the user explicitly asked for midnight."""
        if parsed.get("time") != "00:00":
            return parsed
        if self._should_keep_midnight_time(source_text):
            return parsed
        updated = dict(parsed)
        updated["time"] = None
        return updated

    def _should_keep_midnight_time(self, source_text: str) -> bool:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        client = OpenAI(api_key=self.api_key)
        current_local_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = self._build_midnight_check_prompt(source_text, current_local_datetime)

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                timeout=30
            )

            parsed = json.loads(response.choices[0].message.content)
            self._validate_midnight_check_output(parsed)
            return parsed["keep_midnight_time"]

        except Exception as e:
            logger.warning(f"Midnight confirmation check failed, clearing time defensively: {e}")
            return False

    def _build_midnight_check_prompt(self, source_text: str, current_local_datetime: str) -> str:
        """Build the midnight confirmation prompt."""
        return f"""You decide whether a user's text explicitly asks for midnight. The current local datetime is {current_local_datetime}.

User text:
"{source_text}"

Return a JSON object with this exact field:
- keep_midnight_time: true if the user explicitly asked for midnight or 00:00, otherwise false

Rules:
- The text may be written in any language
- Return true only when midnight is explicitly requested
- If the text only mentions a date or day such as tomorrow, return false
- Return only valid JSON
"""

class TaskParser:
    """
    Main task parser class with pluggable backends.
    
    Usage:
        # Development (local Ollama)
        parser = TaskParser.create()
        
        # Production (OpenAI)
        parser = TaskParser.create(backend="openai", api_key="sk-...")
    """
    
    def __init__(self, backend: TaskParserBackend):
        """Initialize with a backend instance."""
        self.backend = backend
    
    @classmethod
    def create(cls, backend: str = "ollama", **kwargs) -> "TaskParser":
        """
        Factory method to create TaskParser with specified backend.
        
        Args:
            backend: "ollama" or "openai"
            **kwargs: Backend-specific configuration
            
        Returns:
            TaskParser instance
            
        Examples:
            parser = TaskParser.create("ollama")
            parser = TaskParser.create("openai", api_key="sk-...", model="gpt-4o")
        """
        backends = {
            "ollama": OllamaBackend,
            "openai": OpenAIBackend,
        }
        
        if backend not in backends:
            raise ValueError(
                f"Unknown backend: {backend}. "
                f"Choose from: {', '.join(backends.keys())}"
            )
        
        backend_instance = backends[backend](**kwargs)
        return cls(backend_instance)
    
    def parse(self, text: str) -> Dict:
        """
        Parse natural language task description.
        
        Args:
            text: Natural language task description
            
        Returns:
            Structured task dict
            
        Raises:
            RuntimeError: If parsing fails
            ValueError: If output is invalid
        """
        return self.backend.parse(text)

    def resolve_temporal_update(self, task: Dict, answer: str) -> Dict:
        """Resolve a date/time follow-up using the backend."""
        return self.backend.resolve_temporal_update(task, answer)


# Convenience function for quick usage
def parse_task(text: str, backend: str = "ollama", **kwargs) -> Dict:
    """
    Quick function to parse a task.
    
    Args:
        text: Natural language task description
        backend: Backend to use
        **kwargs: Backend configuration
        
    Returns:
        Parsed task dict
    """
    parser = TaskParser.create(backend=backend, **kwargs)
    return parser.parse(text)


def resolve_temporal_update(task: Dict, answer: str, backend: str = "ollama", **kwargs) -> Dict:
    """
    Resolve date/time follow-up text using the current task as context.

    Args:
        task: Current parsed task
        answer: User clarification text
        backend: Backend to use
        **kwargs: Backend configuration

    Returns:
        Dict with date/time values
    """
    parser = TaskParser.create(backend=backend, **kwargs)
    return parser.resolve_temporal_update(task, answer)


def revise_parse(text: str, current_parse: Dict, backend: str = "ollama", **kwargs) -> Dict:
    """
    Make a second conservative parse attempt before asking follow-up questions.

    Args:
        text: Original natural language task description
        current_parse: Current parsed task dict
        backend: Backend to use
        **kwargs: Backend configuration

    Returns:
        Revised parsed task dict
    """
    parser = TaskParser.create(backend=backend, **kwargs)
    return parser.backend.revise_parse(text, current_parse)
