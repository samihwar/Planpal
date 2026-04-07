import subprocess
import json
import re
from datetime import datetime

def parse_task_with_ollama(text: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")

    """
    Uses Ollama's llama3 model to parse a natural language task into a structured JSON object.
    
    Fields returned:
    - title: short summary of the task
    - description: full description
    - due: ISO 8601 timestamp of task start
    - duration: hours as a number
    """

    prompt = f"""
You are a task parser. Today's date is {today}.
Convert the following into a JSON object with these fields:
- title: short summary
- description: full description
- due: ISO 8601 timestamp of start
- duration: hours as a number

If the text has relative dates like "tomorrow" or "next Friday", convert them to real dates based on today.

Input: "{text}"

Output JSON only.
"""
    try:
        # Call Ollama CLI with the prompt as a positional argument
        result = subprocess.run(
            ["ollama", "run", "llama3", prompt],
            capture_output=True,
            text=True,
            check=True
        )

        output_text = result.stdout.strip()

        # Extract JSON using regex
        match = re.search(r"\{.*\}", output_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            # If no JSON found, raise an error to catch it
            raise ValueError(f"No JSON output from Ollama. Output was:\n{output_text}")

    except subprocess.CalledProcessError as e:
        # Ollama CLI failed
        raise RuntimeError(f"Ollama command failed: {e.stderr}") from e
    except json.JSONDecodeError as e:
        # Output was not valid JSON
        raise ValueError(f"Failed to parse JSON. Output was:\n{output_text}") from e


# Quick test
if __name__ == "__main__":
    task_text = "Tomorrow at 10am continue working on Planpal for 2 hours"
    parsed_task = parse_task_with_ollama(task_text)
    print(parsed_task)