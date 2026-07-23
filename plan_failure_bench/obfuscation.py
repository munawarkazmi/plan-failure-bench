"""The obfuscated condition, in the style of Mystery Blocksworld.

Semantic content words are replaced by deterministic nonsense tokens:
entity names, categories, properties, action names, door state words, and
the word portable. The structural formalism vocabulary (room, door, item,
gripper, robot) and the response protocol (plan, infeasible, clarify, the
reason codes) are retained, so the model still knows what kind of object
everything is and how to answer; what it loses is every semantic cue about
what the objects mean.

Soundness by construction: the renaming is a bijection on tokens, applied
to the assembled prompt text and inverted on the model's raw response
before checking. The checker, the seeds, and every label proof operate
only on the canonical world; the obfuscated condition never builds a
second world model that could drift from the first.

Instruction text is natural language, so identifiers alone do not cover
it. A per environment lexicon file supplies a phrase map that normalises
English surface forms to canonical token phrasing before token
substitution (for example "teddy bear" to the item's category, or a
constraint sentence to a rationale free restatement), plus extra tokens
for words that name nothing in the environment (a nonexistent object, an
inexpressible verb's noun) and a leak word list the tests grep for.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

from .schema import Environment, GLOBAL_ACTIONS, SchemaError

OBFUSCATION_SEED = 20260723

_STATE_WORDS = ("open", "closed", "locked")
_SYLLABLES = (
    "vek", "zor", "mul", "tra", "fen", "gol", "pri", "sna", "dur", "kel",
    "bof", "wix", "yam", "ral", "tez", "quo", "pim", "lus", "cra", "hib",
)
_RESERVED = frozenset(
    "room rooms door doors item items robot gripper plan infeasible clarify action "
    "args candidates reason unreachable missing_capability constraint move change "
    "adjacent connects environment instruction".split()
)

_LEXICON_KEYS = {"phrase_map", "extra_tokens", "leak_words"}


@dataclass(frozen=True)
class Obfuscation:
    phrase_map: tuple[tuple[str, str], ...]
    token_map: tuple[tuple[str, str], ...]
    leak_words: tuple[str, ...]

    def apply(self, text: str) -> str:
        return _substitute(_substitute(text, self.phrase_map), self.token_map)

    def invert(self, text: str) -> str:
        return _substitute(text, tuple((t, w) for w, t in self.token_map))

    def token_for(self, word: str) -> str:
        for w, t in self.token_map:
            if w == word:
                return t
        raise KeyError(word)


def _substitute(text: str, pairs: tuple[tuple[str, str], ...]) -> str:
    for src, dst in sorted(pairs, key=lambda p: -len(p[0])):
        # Lookarounds rather than \b: phrase keys can end in punctuation,
        # where \b never matches. \w on either side blocks matches inside
        # identifiers like d_kitchen_hall.
        pattern = re.compile(rf"(?<!\w){re.escape(src)}(?!\w)", re.IGNORECASE)

        def repl(match, dst=dst):
            found = match.group(0)
            if found[:1].isupper():
                return dst[:1].upper() + dst[1:]
            return dst

        text = pattern.sub(repl, text)
    return text


def _make_token(rng: random.Random, taken: set[str]) -> str:
    while True:
        word = "".join(rng.choice(_SYLLABLES) for _ in range(rng.randint(2, 3)))
        if word not in taken:
            return word


def load_lexicon(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw.keys()) != _LEXICON_KEYS:
        raise SchemaError(f"{path}: expected exactly the keys {sorted(_LEXICON_KEYS)}")
    return raw


def build_obfuscation(env: Environment, lexicon: dict) -> Obfuscation:
    rng = random.Random(OBFUSCATION_SEED)
    words: list[str] = []
    for w in (
        list(env.rooms)
        + [d.name for d in env.doors]
        + [i.name for i in env.items]
        + sorted({i.category for i in env.items})
        + sorted({p for i in env.items for p in i.properties})
        + list(GLOBAL_ACTIONS)
        + list(_STATE_WORDS)
        + ["portable"]
        + list(lexicon["extra_tokens"])
    ):
        if w not in words:
            words.append(w)

    taken = set(words) | set(_RESERVED)
    token_map: list[tuple[str, str]] = []
    for w in words:
        t = _make_token(rng, taken)
        taken.add(t)
        token_map.append((w, t))
    # Plural surface forms map to pluralised tokens, so "cups" and
    # "liquids" in prose obfuscate consistently with their singulars.
    token_map += [(w + "s", t + "s") for w, t in token_map if not w.endswith("s")]

    return Obfuscation(
        phrase_map=tuple(lexicon["phrase_map"].items()),
        token_map=tuple(token_map),
        leak_words=tuple(lexicon["leak_words"]),
    )


def load_obfuscation(env: Environment, environments_dir: str | Path) -> Obfuscation:
    lexicon_path = Path(environments_dir) / f"{env.name}.obfuscation.json"
    return build_obfuscation(env, load_lexicon(lexicon_path))
