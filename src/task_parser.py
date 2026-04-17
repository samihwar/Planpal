"""
Task parser with pluggable LLM backends.
Currently uses Ollama locally, ready to scale to cloud LLMs.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict
import json
import logging

logger = logging.getLogger(__name__)    # for debugging and error logging


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
    
    def _validate_output(self, parsed: Dict) -> None:
        """Validate parsed output has required fields."""
        required_fields = {"title", "description", "date", "time", "duration"}
        missing = required_fields - set(parsed.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
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

    def _validate_temporal_output(self, parsed: Dict) -> None:
        """Validate temporal follow-up output."""
        required_fields = {"date", "time"}
        missing = required_fields - set(parsed.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        if parsed["date"] is not None and not isinstance(parsed["date"], str):
            raise ValueError("date must be a YYYY-MM-DD string or null")
        if parsed["time"] is not None and not isinstance(parsed["time"], str):
            raise ValueError("time must be an HH:MM string or null")

    def _validate_midnight_check_output(self, parsed: Dict) -> None:
        """Validate midnight check output."""
        required_fields = {"keep_midnight_time"}
        missing = required_fields - set(parsed.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        if not isinstance(parsed["keep_midnight_time"], bool):
            raise ValueError("keep_midnight_time must be a boolean")


class OllamaBackend(TaskParserBackend):
    """Ollama-based task parser for local development."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        temperature: float = 0,
    ):
        """
        Initialize Ollama backend.
        
        Args:
            base_url: Ollama API endpoint
            model: Model name (llama3, mistral, etc.)
            temperature: Sampling temperature. Lower values are more deterministic.
        """
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        logger.info(f"Initialized Ollama backend: {base_url} with model {model}")
    
    def parse(self, text: str) -> Dict:
        import requests
        
        current_local_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        prompt = self._build_prompt(text, current_local_datetime)
        
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
                timeout=30
            )
            response.raise_for_status()
            
            output = response.json()["response"]
            parsed = json.loads(output)
            
            self._validate_output(parsed)
            parsed = self._clear_unconfirmed_midnight(parsed, text)
            logger.debug(f"Successfully parsed task: {parsed['title']}")
            return parsed
            
        except requests.Timeout:
            logger.error("Ollama request timed out")
            raise RuntimeError("Task parsing timed out. Ollama may be overloaded.")
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

        current_local_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = self._build_temporal_update_prompt(task, answer, current_local_datetime)

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
                timeout=30
            )
            response.raise_for_status()

            output = response.json()["response"]
            parsed = json.loads(output)

            self._validate_temporal_output(parsed)
            parsed = self._clear_unconfirmed_midnight(parsed, answer)
            return parsed

        except requests.Timeout:
            logger.error("Ollama temporal follow-up request timed out")
            raise RuntimeError("Temporal follow-up parsing timed out. Ollama may be overloaded.")
        except requests.ConnectionError:
            logger.error("Cannot connect to Ollama")
            raise RuntimeError("Cannot connect to Ollama. Is it running?")
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            raise RuntimeError(f"Ollama API request failed: {e}") from e
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Ollama temporal follow-up response: {output}")
            raise ValueError(f"Invalid temporal follow-up response from Ollama: {e}") from e
    
    def _build_prompt(self, text: str, current_local_datetime: str) -> str:
        """Build the parsing prompt."""
        return f"""You are a task parser. The current local datetime is {current_local_datetime}.

Convert the following into a JSON object with these exact fields:
- title: short title (max 50 characters)
- description: full description of the task
- date: date only in YYYY-MM-DD format
- time: time only in 24-hour HH:MM format
- duration: hours as a number (e.g., 2.5 for 2.5 hours)

Rules:
- The input may be written in any language and may use casual day-to-day phrasing
- Preserve the user's language in the title and description
- Convert any date expression you can confidently understand into the date field
- Convert any time expression you can confidently understand into the time field using 24-hour HH:MM
- If a time is given without a date, assume the next matching occurrence relative to the current local datetime
- If the user gives only a date or day reference and no time, set time to null
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Keep title and description always filled based on the sentence, even if other details are missing
- If the date is missing or cannot be inferred, use null
- If the time is missing or cannot be inferred, use null
- If the duration is missing or cannot be inferred, use null
- Return only valid JSON and never include markdown or explanations

Input: "{text}"

Output only valid JSON, no explanation or markdown formatting."""

    def _build_temporal_update_prompt(self, task: Dict, answer: str, current_local_datetime: str) -> str:
        """Build the temporal follow-up prompt."""
        task_json = json.dumps(task, ensure_ascii=True)
        return f"""You resolve missing scheduling details for a task. The current local datetime is {current_local_datetime}.

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
- If a time is given without a date, assume the next matching occurrence relative to the current local datetime
- If the clarification gives only a date or day reference and no time, keep time null unless the existing task already has a time
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Return only valid JSON, with no explanation and no markdown
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
                timeout=30
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
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", temperature: float = 0):
        """
        Initialize OpenAI backend.
        
        Args:
            api_key: OpenAI API key
            model: Model name (gpt-4o-mini, gpt-4o, etc.)
            temperature: Sampling temperature. Lower values are more deterministic.
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        logger.info(f"Initialized OpenAI backend with model {model}")
    
    def parse(self, text: str) -> Dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")
        
        client = OpenAI(api_key=self.api_key)
        current_local_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        prompt = self._build_prompt(text, current_local_datetime)
        
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
            parsed = self._clear_unconfirmed_midnight(parsed, text)
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
        current_local_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = self._build_temporal_update_prompt(task, answer, current_local_datetime)

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
            parsed = self._clear_unconfirmed_midnight(parsed, answer)
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

Rules:
- The input may be written in any language
- Preserve the user's language in the title and description
- If a time is given without a date, assume the next matching occurrence relative to the current local datetime
- If the user gives only a date or day reference and no time, set time to null
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Keep title and description always filled
- Use null for missing date, time, or duration

Input: "{text}"

Output only valid JSON."""

    def _build_temporal_update_prompt(self, task: Dict, answer: str, current_local_datetime: str) -> str:
        """Build the temporal follow-up prompt."""
        task_json = json.dumps(task, ensure_ascii=True)
        return f"""You resolve missing scheduling details for a task. The current local datetime is {current_local_datetime}.

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
- If a time is given without a date, assume the next matching occurrence relative to the current local datetime
- If the clarification gives only a date or day reference and no time, keep time null unless the existing task already has a time
- Never invent a default time such as 00:00, midnight, or any other fallback time
- Output 00:00 only if the user explicitly indicates midnight or 00:00
- Return only valid JSON
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
