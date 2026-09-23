"""
Anti-"AI-sounding" checks. Deterministic, so we can score them and feed violations back to the writer.

Three families:
  * BANNED_WORDS  - vocabulary that AI-text detectors and recruiters flag as machine-written
  * PRONOUNS      - "you"/"they" style second/third-person addressing is out; "I"/"we" or implied subject is fine
  * PATTERNS      - stock constructions ("not only ... but also", "in today's fast-paced", em-dash chains ...)
"""
from __future__ import annotations

import re

BANNED_WORDS = [
    "delve", "delved", "delving", "leverage", "leveraged", "leveraging", "robust", "seamless", "seamlessly",
    "spearhead", "spearheaded", "cutting-edge", "state-of-the-art", "synergy", "synergies", "foster", "fostered",
    "fostering", "utilize", "utilized", "utilizing", "streamline", "streamlined", "streamlining", "harness",
    "harnessed", "elevate", "elevated", "empower", "empowered", "empowering", "holistic", "paradigm",
    "meticulous", "meticulously", "tapestry", "realm", "landscape", "navigate", "navigating", "underscore",
    "underscores", "pivotal", "crucial", "vital", "game-changer", "game-changing", "revolutionize",
    "revolutionary", "transformative", "unlock", "unlocking", "unleash", "orchestrate", "orchestrated",
    "orchestrating", "championed", "spearheading", "innovative", "innovatively", "impactful",
    "best-in-class", "world-class", "next-generation", "mission-critical", "bleeding-edge",
    "passionate", "results-driven", "detail-oriented", "proven track record", "thought leader",
    "synergize", "facilitate", "facilitated", "showcase", "showcasing",
    "testament", "embark", "embarked", "journey", "multifaceted", "deliver value",
    "value-add", "solutioning", "utilization", "in order to", "plethora", "myriad", "commendable",
    "noteworthy", "intricate", "intricacies", "nuanced", "furthermore", "moreover", "additionally",
    "consequently", "thus", "hence", "notably", "importantly",
    "meticulousness", "adept", "well-versed", "keen", "skillset", "skill set",
    "collaborated closely", "collaborate closely", "aligning with business goals",
    "aligned with business goals", "scalable solutions", "user-centric", "customer-centric",
    "actionable insights",
]
# legitimate engineering words that AI text over-uses: allowed, but at most once per resume each
OVERUSED_WORDS = [
    "optimize", "optimized", "optimizing", "enhance", "enhanced", "enhancing", "ensure", "ensuring",
    "comprehensive", "dynamic", "stakeholders", "end-to-end", "high-performance", "high-quality",
    "cross-functional", "data-driven", "significantly", "substantially", "drive", "driving", "proficient",
    "scalable", "maintainable", "efficient", "efficiently", "improving", "improved",
]
# a few that are only bad as "filler adverbs" at sentence start
BANNED_OPENERS = ["overall", "in summary", "in conclusion", "ultimately", "essentially", "basically"]

BAD_PRONOUNS = re.compile(r"\b(you|your|yours|they|their|them|he|she|his|her)\b", re.I)

PATTERNS = [
    (re.compile(r"\bnot only\b.*\bbut also\b", re.I), "'not only ... but also' construction"),
    (re.compile(r"\bin today'?s\b", re.I), "'in today's ...' opener"),
    (re.compile(r"—|\s--\s|(?<=[A-Za-z])\s+–\s+(?=[A-Za-z])"),
     "em dash (rewrite the aside as a grammatical sentence, such as '. That is ...'; do not just replace — with a comma)"),
    (re.compile(r"\bresulting in\b", re.I), "'resulting in' outcome clause (use a plain verb + number)"),
    (re.compile(r"\bthereby\b", re.I), "'thereby'"),
    (re.compile(r"\bwhile (also )?(ensuring|maintaining|fostering|driving)\b", re.I), "'while ensuring/maintaining...' tail"),
    (re.compile(r"\b(a|the) (wide|broad|diverse) (range|array|variety) of\b", re.I), "'a wide range of'"),
    (re.compile(r"\bplay(ed|s)? a (key|pivotal|crucial|vital) role\b", re.I), "'played a key role'"),
    (re.compile(r"\bcontinuous improvement\b", re.I), "'continuous improvement'"),
    (re.compile(r"\b(significant|substantial) (improvement|increase|reduction)s?\b", re.I),
     "vague 'significant improvement' (give the number instead)"),
]


def _word_re(w: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", re.I)


_BANNED_RES = [(w, _word_re(w)) for w in BANNED_WORDS]
_OVERUSED_RES = [(w, _word_re(w)) for w in OVERUSED_WORDS]


def find_flags(text: str) -> list[str]:
    """Return human-readable violations found in text."""
    flags: list[str] = []
    for w, rx in _BANNED_RES:
        if rx.search(text):
            flags.append(f"word: {w}")
    for w, rx in _OVERUSED_RES:
        n = len(rx.findall(text))
        if n > 1:
            flags.append(f"overused: {w} x{n} (max 1)")
    for m in BAD_PRONOUNS.finditer(text):
        flags.append(f"pronoun: {m.group(0)}")
    for rx, label in PATTERNS:
        if rx.search(text):
            flags.append(f"pattern: {label}")
    for op in BANNED_OPENERS:
        if re.search(r"(^|[.!?]\s+)" + op + r"\b", text, re.I):
            flags.append(f"opener: {op}")
    # de-duplicate keeping order
    seen = set()
    out = []
    for f in flags:
        if f.lower() not in seen:
            seen.add(f.lower())
            out.append(f)
    return out


_EM_DASH = re.compile(r"\s*(?:—|--)\s*|(?<=[A-Za-z])\s+–\s+(?=[A-Za-z])")
_FINITE = re.compile(
    r"\b(is|are|was|were|has|have|had|do|does|did|built|kept|added|owned|worked|took|ran|went|made|fixed|wrote|used|showed|became|left|found|cut|moved|rewrote)\b",
    re.I,
)
_REL = re.compile(r"\b(where|when|which|who|that)\b", re.I)


def _noun_phrase_aside(right: str) -> bool:
    """True when the text after the dash has no main verb, so a comma would leave a fragment."""
    head = _REL.split(right, maxsplit=1)[0].split(",")[0]
    return _FINITE.search(head) is None


def _join_aside(left: str, right: str) -> str:
    left = left.rstrip(" ,;:")
    right = right.strip()
    if not right:
        return left
    glue = " " if left.endswith((".", "!", "?")) else ". "
    if _noun_phrase_aside(right):
        if right[0].isupper() and not right.startswith(("I", "I'")):
            right = right[0].lower() + right[1:]
        if not right.endswith((".", "!", "?")):
            right += "."
        return f"{left}{glue}That is {right}"
    if right[0].islower():
        right = right[0].upper() + right[1:]
    return f"{left}{glue}{right}"


def drop_em_dashes(text: str) -> str:
    """Rewrite an em-dash aside into a sentence. A bare comma is not a substitute.

    'failures — the part of the month' becomes 'failures. That is the part of the month.'
    A full clause after the dash becomes its own sentence. Hyphens in 'real-time' stay,
    and date ranges like '2020 – 2024' stay.
    """
    if not text or not _EM_DASH.search(text):
        return text
    parts = _EM_DASH.split(text)
    out = parts[0].rstrip()
    for right in parts[1:]:
        out = _join_aside(out, right)
    return re.sub(r"\s{2,}", " ", out).strip()


def readability(text: str) -> dict:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    long_words = [w for w in words if len(w) >= 13]
    avg = (len(words) / len(sentences)) if sentences else 0
    return {
        "sentences": len(sentences),
        "words": len(words),
        "avg_sentence_words": round(avg, 1),
        "long_word_ratio": round(len(long_words) / max(1, len(words)), 3),
    }


HUMAN_RULES = """WRITING RULES (hard constraints - the output is checked mechanically):
1. Write like an engineer describing their own work to another engineer, not like a marketing page.
   Short, concrete, sometimes a little uneven. Name real components (queue names, services, tables,
   endpoints, dashboards), real failure modes (timeouts, stale cache, double charge, N+1, race on retry,
   memory spike after deploy), and what was measured.
2. Pronouns: never address anyone as "you"; never use "they/their/them/he/she". Implied first person
   (no pronoun) or "I"/"we" only.
3. Do NOT use any of these words or phrases (or their inflections): """ + ", ".join(BANNED_WORDS) + """.
   Use each of these at most ONCE in the whole resume: """ + ", ".join(OVERUSED_WORDS) + """.
4. Do not stack adjectives. No "not only ... but also". No "resulting in"; say what happened with a number
   or a plain outcome ("p95 dropped from 900ms to 300ms", "on-call pages went from ~10 a week to 2").
5. Numbers should be plausible and specific but not every bullet needs one; 40-60% of bullets with a number
   is realistic. Vary sentence openers; do not start more than two consecutive bullets with the same verb.
6. Use normal everyday vocabulary ("fixed", "moved", "rewrote", "cut", "added", "found", "kept") instead of
   inflated verbs. Mention trade-offs or things that did not work once in a while - that is how people write.
7. Use each ATS keyword naturally where it is true for the role; never keyword-stuff a sentence.
8. Never use an em dash (—) or a spaced double hyphen (--). Do not merely swap it for a comma; that leaves a fragment.
   Wrong: "payout failures — the part of the month where money has to land on time."
   Wrong: "payout failures, the part of the month where money has to land on time."
   Right: "payout failures. That is the part of the month where money has to land on time."
   If the words after the dash are already a full clause, give them their own sentence.
   Hyphens inside a word (real-time, multi-currency) are fine. Date ranges keep their en dash."""
