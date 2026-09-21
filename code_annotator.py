"""Token-level Lean code annotation with documentation-first lookups."""

from dataclasses import dataclass
from pathlib import Path
import re

from agent import load_skill


# These sets turn raw tokens into labels that are understandable to Lean learners.
KEYWORDS = {
    "axiom", "class", "coinductive", "def", "deriving", "else", "example", "extends",
    "if", "import", "inductive", "instance", "let", "match", "namespace", "open",
    "abbrev", "axiom", "class", "opaque", "private", "protected", "section",
    "structure", "theorem", "variable", "where", "with",
    "by", "do", "else", "fun", "forall", "have", "show", "suffices", "calc",
}
TACTICS = {
    "apply", "assumption", "cases", "constructor", "contradiction", "decide", "exact",
    "induction", "intro", "left", "omega", "rfl", "rw", "simp", "simp_all", "tauto",
    "trivial", "unhygienic", "right", "use",
}
SYNTAX = {"(", ")", "[", "]", "{", "}", ":", ",", ";", ".", "|", "_", ":="}
NOTATION = {
    "!", "#", "$", "%", "&", "'", "*", "+", "-", "/", "<", ">", "=", "?", "@", "^",
    "~", "→", "←", "↔", "≤", "≥", "≠", "∧", "∨", "∈", "⊢", "=>", "->", "<>",
}
NUMBER_RE = re.compile(r"(?:0[bB][01]+|0[oO][0-7]+|0[xX][0-9A-Fa-f]+|[0-9]+(?:\.[0-9]+)?)\Z")
IDENTIFIER_RE = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_']*|[α-ωΑ-Ω][A-Za-z0-9_']*)\Z")


@dataclass(frozen=True)
class AnnotatedToken:
    # Line and column positions let the caller relate a label back to the source code.
    text: str
    category: str
    line: int
    column: int
    documentation_found: bool


@dataclass(frozen=True)
class CodeAnnotation:
    code: str
    tokens: tuple[AnnotatedToken, ...]
    searches: tuple[str, ...]
    sources: tuple[str, ...]
    documentation_checked: bool


class LeanCodeAnnotator:
    def __init__(self, index, skill_path: Path):
        self.index = index
        self.skill = load_skill(skill_path)

    def annotate(self, code: str) -> CodeAnnotation:
        # Documentation is checked before classification to preserve the project's core rule.
        raw_tokens = tokenize_lean(code)
        annotated: list[AnnotatedToken] = []
        searches: list[str] = []
        sources: list[str] = []
        for raw in raw_tokens:
            # Lookup occurs before the category is produced, so the label is
            # an explanation layer over the documentation-checking pipeline.
            results = self.index.search(raw.text, top_k=1)
            searches.append(raw.text)
            found = bool(results)
            if found and results[0].url not in sources:
                sources.append(results[0].url)
            annotated.append(
                AnnotatedToken(raw.text, classify_token(raw.text), raw.line, raw.column, found)
            )
        return CodeAnnotation(code, tuple(annotated), tuple(searches), tuple(sources), True)


@dataclass(frozen=True)
class _RawToken:
    text: str
    line: int
    column: int


def tokenize_lean(code: str) -> list[_RawToken]:
    # A small tokenizer is enough for explanation; a full Lean parser would add unnecessary runtime complexity.
    tokens: list[_RawToken] = []
    index = 0
    line = 1
    column = 1
    # Longer operators must be recognized before their individual characters.
    multi = (":=", "=>", "->", "<>", "≤", "≥", "≠", "→", "←", "↔", "∧", "∨", "∈", "⊢")
    while index < len(code):
        char = code[index]
        if char in " \t\r":
            index += 1
            column += 1
            continue
        if char == "\n":
            index += 1
            line += 1
            column = 1
            continue
        if code.startswith("--", index):
            # Line comments are ignored as executable tokens and handled as documentation items elsewhere.
            while index < len(code) and code[index] != "\n":
                index += 1
                column += 1
            continue
        start_line, start_column = line, column
        if char == '"':
            # Keep quoted text together so a string is reported as one literal.
            end = index + 1
            while end < len(code) and code[end] != '"':
                end += 2 if code[end] == "\\" else 1
            end = min(end + 1, len(code))
            value = code[index:end]
        elif code.startswith("#", index):
            # Commands such as #check and #eval are single Lean tokens for annotation purposes.
            match = re.match(r"#[A-Za-z][A-Za-z0-9_]*", code[index:])
            value = match.group(0) if match else "#"
        elif any(code.startswith(operator, index) for operator in multi):
            value = next(operator for operator in multi if code.startswith(operator, index))
        elif char.isalnum() or char in "_αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ":
            match = re.match(r"[A-Za-z0-9_α-ωΑ-Ω']+", code[index:])
            value = match.group(0)
        else:
            value = char
        tokens.append(_RawToken(value, start_line, start_column))
        index += len(value)
        column += len(value)
    return tokens


def classify_token(token: str) -> str:
    # The order matters: for example, "simp" is both a word and a tactic identifier.
    if token.startswith('"') and token.endswith('"'):
        return "string"
    if token in KEYWORDS:
        return "keyword"
    if token in TACTICS:
        return "tactic identifier"
    if token in SYNTAX or token.startswith("#"):
        return "syntax"
    if NUMBER_RE.fullmatch(token):
        return "numeral"
    if token in NOTATION:
        return "notation"
    if IDENTIFIER_RE.fullmatch(token):
        return "identifier"
    return "syntax"
