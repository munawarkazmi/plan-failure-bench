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

_RESPONSE_SHAPES = ({"plan"}, {"infeasible"}, {"clarify"})


def extract_first_json_object(text: str) -> str | None:
    """The first balanced, parseable, response-shaped JSON object, or None.

    Response-shaped means exactly one of the three top level keys the DSL
    defines. Without that restriction, a truncated response whose outer
    object never closes would yield some inner fragment (a single plan
    step, say), which is not the model's answer to anything.
    """
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
                        parsed = json.loads(candidate)
                    except ValueError:
                        break
                    if isinstance(parsed, dict) and set(parsed.keys()) in _RESPONSE_SHAPES:
                        return candidate
                    break
        start = text.find("{", start + 1)
    return None
