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
                - due (str): ISO 8601 timestamp
                - duration (float): hours as number
                
        Raises:
            RuntimeError: If LLM service fails
            ValueError: If output is invalid
        """
        pass
    
    def _validate_output(self, parsed: Dict) -> None:
        """Validate parsed output has required fields."""
        required_fields = {"title", "description", "due", "duration"}
        missing = required_fields - set(parsed.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
        # Type validation
        if not isinstance(parsed["title"], str):
            raise ValueError("title must be a string")
        if not isinstance(parsed["description"], str):
            raise ValueError("description must be a string")
        if not isinstance(parsed["due"], str):
            raise ValueError("due must be an ISO 8601 string")
        if not isinstance(parsed["duration"], (int, float)):
            raise ValueError("duration must be a number")


class OllamaBackend(TaskParserBackend):
    """Ollama-based task parser for local development."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        """
        Initialize Ollama backend.
        
        Args:
            base_url: Ollama API endpoint
            model: Model name (llama3, mistral, etc.)
        """
        self.base_url = base_url
        self.model = model
        logger.info(f"Initialized Ollama backend: {base_url} with model {model}")
    
    def parse(self, text: str) -> Dict:
        import requests
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        prompt = self._build_prompt(text, today)
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=30
            )
            response.raise_for_status()
            
            output = response.json()["response"]
            parsed = json.loads(output)
            
            self._validate_output(parsed)
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
    
    def _build_prompt(self, text: str, today: str) -> str:
        """Build the parsing prompt."""
        return f"""You are a task parser. Today's date is {today}.

Convert the following into a JSON object with these exact fields:
- title: short summary (max 100 characters)
- description: full description of the task
- due: ISO 8601 timestamp of when task starts (e.g., "2025-04-09T10:00:00")
- duration: hours as a number (e.g., 2.5 for 2.5 hours)

Rules:
- Convert relative dates ("tomorrow", "next Friday") to absolute dates based on today
- If no time specified, use 09:00:00 as default
- If no duration specified, use 1.0 hour as default

Input: "{text}"

Output only valid JSON, no explanation or markdown formatting."""


class OpenAIBackend(TaskParserBackend):
    """OpenAI-based task parser for production scale."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Initialize OpenAI backend.
        
        Args:
            api_key: OpenAI API key
            model: Model name (gpt-4o-mini, gpt-4o, etc.)
        """
        self.api_key = api_key
        self.model = model
        logger.info(f"Initialized OpenAI backend with model {model}")
    
    def parse(self, text: str) -> Dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")
        
        client = OpenAI(api_key=self.api_key)
        today = datetime.now().strftime("%Y-%m-%d")
        
        prompt = self._build_prompt(text, today)
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30
            )
            
            parsed = json.loads(response.choices[0].message.content)
            self._validate_output(parsed)
            logger.debug(f"Successfully parsed task: {parsed['title']}")
            return parsed
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI API request failed: {e}") from e
    
    def _build_prompt(self, text: str, today: str) -> str:
        """Build the parsing prompt."""
        return f"""You are a task parser. Today's date is {today}.

Convert the following into a JSON object with these exact fields:
- title: short summary
- description: full description
- due: ISO 8601 timestamp of start
- duration: hours as a number

Input: "{text}"

Output only valid JSON."""

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


if __name__ == "__main__":
    # Setup logging for testing
    logging.basicConfig(level=logging.DEBUG)
    
    # Test with Ollama
    print("Testing with Ollama backend...")
    parser = TaskParser.create(backend="ollama")
    
    test_cases = [
        "Tomorrow at 10am continue working on Planpal for 2 hours",
        "Review PR next Monday at 2pm for 30 minutes",
        "Call mom this Friday at 5pm",
    ]
    
    for task_text in test_cases:
        print(f"\nInput: {task_text}")
        try:
            result = parser.parse(task_text)
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error: {e}")