"""Documentation-grounded structural explanation of Lean 4 code."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from agent import load_skill
from code_annotator import SYNTAX, TACTICS, KEYWORDS, classify_token, tokenize_lean
from docs_index import SearchResult


# These names identify declaration lines so the final explanation can describe their role.
COMMANDS = {
    "abbrev", "axiom", "class", "def", "example", "inductive", "instance", "namespace",
    "opaque", "section", "structure", "theorem", "variable",
}
# Common built-in types get a clear type label instead of a generic identifier label.
TYPE_NAMES = {"Nat", "Int", "Bool", "String", "Prop", "Type", "Sort", "List", "Option"}
META_COMMANDS = {"#check", "#eval", "#print", "#reduce", "#synth"}
DOCUMENTATION_CATEGORY = "Comments/docstrings/macros/syntax extensions"


@dataclass(frozen=True)
class CodeThing:
    # A CodeThing is the unit that gets documented before translation.
    text: str
    category: str
    line: int
    column: int
    documentation: tuple[SearchResult, ...] = ()


@dataclass(frozen=True)
class CodeExplanation:
    # Store both the explanation and its evidence so callers can inspect the full process.
    code: str
    things: tuple[CodeThing, ...]
    searches: tuple[str, ...]
    sources: tuple[str, ...]
    context: str
    english: str
    documentation_checked: bool
    skill_loaded: bool


class CodeTranslator:
    def translate(self, code: str, context: str) -> str:
        raise NotImplementedError


class ExtractiveCodeTranslator(CodeTranslator):
    def translate(self, code: str, context: str) -> str:
        # This predictable fallback provides useful output without an external model.
        things = extract_code_things(code)
        command_index = next(
            (index for index, thing in enumerate(things) if thing.category == "Commands/declarations"),
            None,
        )
        command = things[command_index].text if command_index is not None else None
        name = "the declaration"
        if command_index is not None:
            name = next(
                (
                    thing.text
                    for thing in things[command_index + 1 :]
                    if thing.line == things[command_index].line
                    and thing.category in {"Identifiers / names", "Types"}
                    and thing.text not in KEYWORDS
                ),
                name,
            )
        binder = next((thing.text for thing in things if thing.category == "Binders"), None)
        expressions = [thing.text for thing in things if thing.category == "Terms / expressions"]
        expression = (expressions[-1] if command == "def" and expressions else expressions[0] if expressions else None)
        tactics = [thing.text for thing in things if thing.category == "Tactics"]
        if command == "theorem":
            details = f" It has the binder {binder}." if binder else ""
            statement = f" Its statement is {expression}." if expression else ""
            proof = f" The proof uses {', '.join(tactics)}." if tactics else ""
            return f"This declares a theorem named {name}.{details}{statement}{proof}"
        if command == "def" and any(thing.text == "match" for thing in things):
            return f"This defines {name} using pattern matching."
        if command == "def":
            return f"This defines {name}" + (f" as {expression}." if expression else ".")
        if command in {"inductive", "structure", "class"}:
            return f"This declares {command} {name}. The declaration introduces a new Lean type or interface."
        described = ", ".join(dict.fromkeys(thing.category for thing in things))
        return f"This Lean code contains {described.lower()}."


class OpenAICodeTranslator(CodeTranslator):
    def __init__(self, api_key: str, model: str, endpoint: str, timeout: float = 30):
        self.api_key, self.model, self.endpoint, self.timeout = api_key, model, endpoint, timeout

    def translate(self, code: str, context: str) -> str:
        # The prompt includes retrieved context so the model explains documented facts, not guesses.
        prompt = (
            "Translate this Lean 4 code into clear English. Explain its declarations, binders, "
            "types, terms, tactics, and proof meaning. Use only the documentation context provided.\n\n"
            f"CODE:\n{code}\n\nDOCUMENTATION CONTEXT:\n{context}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            value = json.loads(response.read().decode())
        return value["choices"][0]["message"]["content"].strip()


def code_translator_from_environment() -> CodeTranslator:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        # API access is optional; local execution must still work.
        return ExtractiveCodeTranslator()
    return OpenAICodeTranslator(
        key,
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
    )


class DocumentationFirstCodeAgent:
    def __init__(self, index, translator: CodeTranslator | None, skill_path: Path):
        self.index = index
        self.translator = translator or ExtractiveCodeTranslator()
        self.skill = load_skill(skill_path)

    def explain(self, code: str) -> CodeExplanation:
        # Extract first, document every item second, and translate only after context is complete.
        things = extract_code_things(code)
        documented: list[CodeThing] = []
        searches: list[str] = []
        sources: list[str] = []
        context_lines: list[str] = []
        for thing in things:
            if not thing.text.strip():
                continue
            searches.append(thing.text)
            results = tuple(self.index.search(thing.text, top_k=3))
            documented.append(CodeThing(thing.text, thing.category, thing.line, thing.column, results))
            for result in results:
                if result.url not in sources:
                    sources.append(result.url)
                context_lines.append(f"[{thing.category}] {thing.text}: {result.text}")
        context = "\n".join(dict.fromkeys(context_lines))
        # Translation is deliberately the final step: it receives code plus
        # documentation context, never the raw code as an ungrounded prompt.
        english = self.translator.translate(code, context)
        return CodeExplanation(
            code, tuple(documented), tuple(searches), tuple(sources), context,
            english, True, self.skill.loaded,
        )


def extract_code_things(code: str) -> list[CodeThing]:
    # Token-level items provide detail; grouped ranges add Lean concepts such as binders and expressions.
    raw = tokenize_lean(code)
    things: list[CodeThing] = []
    for token in raw:
        category = _token_category(token.text)
        things.append(CodeThing(token.text, category, token.line, token.column))

    by_line: dict[int, list] = {}
    for token in raw:
        by_line.setdefault(token.line, []).append(token)
    for line, tokens in by_line.items():
        if not tokens:
            continue
        first = tokens[0].text
        if first in COMMANDS or first in META_COMMANDS:
            # Commands/declarations are recorded separately from their keyword token.
            things.append(CodeThing(first, "Commands/declarations", line, tokens[0].column))
        if first in {"syntax", "macro", "elab", "scoped"}:
            # These constructs control Lean's extensible syntax and belong to the documentation category.
            things.append(CodeThing(" ".join(token.text for token in tokens), DOCUMENTATION_CATEGORY, line, tokens[0].column))
        for start, end in _binder_ranges(tokens):
            things.append(CodeThing(_format_tokens(tokens[start:end]), "Binders", line, tokens[start].column))
        for start, end in _expression_ranges(tokens):
            things.append(CodeThing(_format_tokens(tokens[start:end]), "Terms / expressions", line, tokens[start].column))
    for line_number, source_line in enumerate(code.splitlines(), 1):
        stripped = source_line.strip()
        if "--" in stripped:
            # Comments are included because the requested breakdown covers documentation too.
            comment = stripped[stripped.index("--"):].strip()
            things.append(CodeThing(comment, DOCUMENTATION_CATEGORY, line_number, source_line.index("--") + 1))
        if "/-" in stripped or "-/" in stripped:
            comment = stripped[stripped.find("/-"):].strip()
            things.append(CodeThing(comment, DOCUMENTATION_CATEGORY, line_number, source_line.index("/-") + 1))
    return sorted(things, key=lambda thing: (thing.line, thing.column, thing.category != "Commands/declarations"))


def _token_category(token: str) -> str:
    # Reuse the token classifier so annotation mode and explanation mode agree.
    category = classify_token(token)
    if category == "keyword":
        return "Keywords"
    if category == "tactic identifier":
        return "Tactics"
    if category == "numeral" or category == "string":
        return "Literals"
    if category == "notation":
        return "Symbols / notation"
    if category == "syntax":
        return "Syntax"
    if token in TYPE_NAMES or (token and token[0].isupper()):
        return "Types"
    return "Identifiers / names"


def _binder_ranges(tokens: list) -> list[tuple[int, int]]:
    # Parenthesis matching identifies typed binders such as (n : Nat).
    ranges = []
    stack: list[int] = []
    for index, token in enumerate(tokens):
        if token.text in {"(", "{", "["}:
            stack.append(index)
        elif token.text in {")", "}", "]"} and stack:
            start = stack.pop()
            if any(item.text == ":" for item in tokens[start : index + 1]):
                ranges.append((start, index + 1))
    return ranges


def _expression_ranges(tokens: list) -> list[tuple[int, int]]:
    # The type before := and the value after := are the most useful expression ranges.
    ranges = []
    assignment = next((index for index, token in enumerate(tokens) if token.text == ":="), None)
    if assignment is not None and assignment + 1 < len(tokens):
        ranges.append((assignment + 1, len(tokens)))
    if assignment is not None:
        colons = [index for index, token in enumerate(tokens[:assignment]) if token.text == ":"]
        if colons:
            start = colons[-1] + 1
            if start < assignment:
                ranges.insert(0, (start, assignment))
    return ranges


def _format_tokens(tokens: list) -> str:
    text = " ".join(token.text for token in tokens)
    for left in ("(", "[", "{"):
        text = text.replace(left + " ", left)
    for right in (")", "]", "}", ","):
        text = text.replace(" " + right, right)
    return text
