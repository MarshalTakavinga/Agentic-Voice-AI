"""ASR-noise injection: turn clean scripted utterances into what speech recognition really emits.

Each profile is deterministic for a given seed, so a failing variant reproduces exactly.

Profiles fall into three classes, and the class decides what a variant must prove:

* **benign**: the words a caller meant are unchanged; only their surface form differs
  (fillers, punctuation, "oh" for zero). The scenario's full expectations still apply.
* **stress**: realistic but harder errors (homophones such as "for" for "four", digits split
  into groups). Expectations still apply; results are reported, and by default not gated.
* **corrupting**: the caller's identifier itself is garbled (a digit dropped or changed). No
  task can be expected to succeed; the variant proves the agent stays *safe*: it does not verify
  the caller and does not reveal anything only a verified caller may hear.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable
from dataclasses import dataclass

from vae.scenario import FinalExpect, Safety, Scenario, TurnExpect

DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
WORDS_FOR_DIGIT = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
# What recognizers commonly emit for a spoken digit with a same-sounding word.
HOMOPHONES = {"two": "to", "four": "for", "eight": "ate", "one": "won"}
FILLERS = ["um", "uh", "er", "hmm"]

_DIGIT_RUN = re.compile(r"\d{3,}")
_TOKEN = re.compile(r"[A-Za-z']+|\d+|[^\sA-Za-z\d]")


def _rng(seed: int, *parts: str) -> random.Random:
    digest = hashlib.sha256("|".join([str(seed), *parts]).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))  # noqa: S311 - reproducible test noise, not crypto


def _spoken_digit_runs(words: list[str]) -> list[tuple[int, int]]:
    """Index ranges [start, end) of three or more consecutive spoken digit words."""
    runs, start = [], None
    for i, w in enumerate([*words, ""]):
        if w.lower() in DIGIT_WORDS and w.lower() not in {"o"}:
            start = i if start is None else start
        else:
            if start is not None and i - start >= 3:
                runs.append((start, i))
            start = None
    return runs


def _digits_to_words(text: str, zero: str = "zero", homophones: bool = False) -> str:
    def spell(m: re.Match[str]) -> str:
        words = [zero if d == "0" else WORDS_FOR_DIGIT[int(d)] for d in m.group()]
        if homophones:
            words = [HOMOPHONES.get(w, w) for w in words]
        return " ".join(words)

    return _DIGIT_RUN.sub(spell, text)


# --- benign -----------------------------------------------------------------------------------


def fillers(text: str, rng: random.Random) -> str:
    words = text.split()
    if len(words) < 2:
        return text
    pos = rng.randrange(1, len(words))
    words.insert(pos, rng.choice(FILLERS))
    return f"{rng.choice(FILLERS)} " + " ".join(words)


def asr_punctuation(text: str, rng: random.Random) -> str:
    """Hosted recognizers return sentence case and a final period ("Check my balance.")."""
    if not re.search(r"[A-Za-z]", text):
        return text
    out = text[0].upper() + text[1:]
    return out if out.endswith((".", "?", "!")) else out + rng.choice([".", ".", "?"])


def spoken_digits(text: str, rng: random.Random) -> str:
    return _digits_to_words(text)


def written_digits(text: str, rng: random.Random) -> str:
    words = text.split()
    for start, end in reversed(_spoken_digit_runs(words)):
        words[start:end] = ["".join(DIGIT_WORDS[w.lower()] for w in words[start:end])]
    return " ".join(words)


def oh_for_zero(text: str, rng: random.Random) -> str:
    """Callers read zeros as "oh" ("one oh oh oh ..."), in spoken and written turns alike."""
    if not re.search(r"0|\bzero\b", text, flags=re.IGNORECASE):
        return text
    out = _digits_to_words(text, zero="oh")
    return re.sub(r"\bzero\b", "oh", out, flags=re.IGNORECASE)


def stutter(text: str, rng: random.Random) -> str:
    """Repeats the first word, unless it is part of an identifier: "one one zero ..." is a
    different number, so that belongs to the corrupting profiles, not here."""
    words = text.split()
    first = words[0].lower().strip(",.") if words else ""
    if len(words) < 2 or not first.isalpha() or first in DIGIT_WORDS:
        return text
    return " ".join([words[0], *words])


# --- stress -----------------------------------------------------------------------------------


def homophones(text: str, rng: random.Random) -> str:
    out = _digits_to_words(text, homophones=True)
    return re.sub(
        r"\b(two|four|eight|one)\b", lambda m: HOMOPHONES[m.group().lower()], out, flags=re.I
    )


def digit_grouping(text: str, rng: random.Random) -> str:
    """Recognizers often split long numbers ("1000 0001", "100-0001")."""

    def group(m: re.Match[str]) -> str:
        s = m.group()
        if len(s) < 6:
            return s
        cut = len(s) // 2
        return s[:cut] + rng.choice([" ", "-"]) + s[cut:]

    return _DIGIT_RUN.sub(group, text)


# --- corrupting -------------------------------------------------------------------------------


DIGIT_WORD_SET = set(DIGIT_WORDS)


def _rejoin(tokens: list[str], spoken: bool) -> str:
    if spoken:
        return " ".join(tokens)
    text = ""
    for t in tokens:  # written digits rejoin into one run; words keep their spaces
        if t.isdigit() and text and text[-1].isdigit():
            text += t
        else:
            text += ("" if not text else " ") + t
    return text


def _explode(text: str) -> tuple[list[str], list[int], bool]:
    tokens = _TOKEN.findall(text)
    out: list[str] = []
    for t in tokens:
        out.extend(list(t) if t.isdigit() else [t])
    idx = [i for i, t in enumerate(out) if t.isdigit() or t.lower() in DIGIT_WORD_SET - {"o"}]
    spoken = any(not out[i].isdigit() for i in idx)
    return out, idx, spoken


def drop_digit(text: str, rng: random.Random) -> str:
    tokens, idx, spoken = _explode(text)
    if len(idx) < 2:
        return text
    del tokens[rng.choice(idx)]
    return _rejoin(tokens, spoken)


def swap_digit(text: str, rng: random.Random) -> str:
    tokens, idx, spoken = _explode(text)
    if not idx:
        return text
    i = rng.choice(idx)
    current = tokens[i] if tokens[i].isdigit() else DIGIT_WORDS[tokens[i].lower()]
    new = rng.choice([d for d in "0123456789" if d != current])
    tokens[i] = new if tokens[i].isdigit() else WORDS_FOR_DIGIT[int(new)]
    return _rejoin(tokens, spoken)


@dataclass(frozen=True)
class Profile:
    name: str
    category: str  # benign | stress | corrupting
    fn: Callable[[str, random.Random], str]
    description: str


PROFILES: dict[str, Profile] = {
    p.name: p
    for p in [
        Profile("fillers", "benign", fillers, 'Hesitations: "um, I uh want my balance"'),
        Profile("asr_punctuation", "benign", asr_punctuation, "Sentence case and a final period"),
        Profile("spoken_digits", "benign", spoken_digits, "Keyed digits read aloud as words"),
        Profile("written_digits", "benign", written_digits, "Spoken digit words returned as 123"),
        Profile("oh_for_zero", "benign", oh_for_zero, 'Zero said as "oh"'),
        Profile("stutter", "benign", stutter, "First word repeated"),
        Profile("homophones", "stress", homophones, '"for" for four, "to" for two, "won", "ate"'),
        Profile("digit_grouping", "stress", digit_grouping, 'Long numbers split: "1000 0001"'),
        Profile("drop_digit", "corrupting", drop_digit, "One digit of an identifier lost"),
        Profile("swap_digit", "corrupting", swap_digit, "One digit of an identifier misheard"),
    ]
}


def _noisy(scenario: Scenario, profile: Profile, seed: int) -> Scenario | None:
    rng = _rng(seed, scenario.id, profile.name)
    turns = list(scenario.turns)
    changed = False
    if profile.category == "corrupting":
        target = next((i for i, t in enumerate(turns) if t.credential), None)
        if target is None:
            return None
        t = turns[target]
        new_text = profile.fn(t.text, rng)
        if new_text == t.text:
            return None
        field = "dtmf" if t.dtmf is not None else "say"
        if field == "dtmf" and not re.fullmatch(r"[0-9*#]{1,32}", new_text):
            return None
        turns[target] = t.model_copy(update={field: new_text, "expect": TurnExpect()})
        # Expectations after a garbled identifier no longer describe a correct agent.
        turns = turns[: target + 1] + [
            x.model_copy(update={"expect": TurnExpect()}) for x in turns[target + 1 :]
        ]
        safety = Safety(
            must_not_say=[*scenario.safety.must_not_say, *scenario.safety.verified_only],
            forbidden_tools=scenario.safety.forbidden_tools,
        )
        expect = FinalExpect(authenticated=False)
        changed = True
    else:
        for i, t in enumerate(turns):
            if not t.is_speech:
                continue  # DTMF is exact; silence has no words
            new_text = profile.fn(t.text, rng)
            if new_text != t.text:
                turns[i] = t.model_copy(update={"say": new_text})
                changed = True
        safety, expect = scenario.safety, scenario.expect
    if not changed:
        return None
    return scenario.model_copy(
        update={
            "id": f"{scenario.id}~{profile.name}",
            "turns": turns,
            "expect": expect,
            "safety": safety,
            "category": profile.category,
            "base_id": scenario.id,
            "profile": profile.name,
        }
    )


def make_variants(scenarios: list[Scenario], profile_names: list[str], seed: int) -> list[Scenario]:
    """Noise variants of every eligible clean scenario. Profiles that change nothing in a
    scenario (no speech to alter, no identifier to garble) produce no variant."""
    unknown = sorted(set(profile_names) - set(PROFILES))
    if unknown:
        raise ValueError(f"unknown noise profiles: {unknown}; known: {sorted(PROFILES)}")
    out: list[Scenario] = []
    for s in scenarios:
        if not s.noise or s.category != "clean":
            continue
        for name in profile_names:
            v = _noisy(s, PROFILES[name], seed)
            if v is not None:
                out.append(v)
    return out
