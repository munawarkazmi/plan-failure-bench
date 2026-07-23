"""Response extraction policies.

Strict is the primary policy and lives in dsl.py: the response must be the
JSON object alone, optionally fenced. This module adds the lenient policy
used only for offline re-scoring: find the first balanced JSON object
anywhere in the response text. It recovers answers from models that emit
correct JSON wrapped in prose, and it is applied identically to every
model, so it measures planning with format discipline factored out rather
than quietly favouring chatty models.
"""

from __future__ import annotations

import json


def extract_first_json_object(text: str) -> str | None:
    """The first balanced, parseable JSON object in text, or None."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            c = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_string = False
            elif c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None
