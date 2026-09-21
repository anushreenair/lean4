# Lean Documentation-First Agent

This is a small Python prototype that makes official Lean documentation lookup a prerequisite for every answer. It records every input word, extracts general multi-word phrases, searches a locally cached documentation index, retries with a focused query when the first result is weak, and preserves the documentation sources used.

The default explanation layer is extractive, so it works without an LLM API key. If `OPENAI_API_KEY` is set, the optional OpenAI-compatible provider receives only the retrieved documentation context and the user question; provider failures fall back to the extractive answer.

## Architecture

`docs_loader.py` crawls from `LEAN_DOCS_BASE_URL` (default: the official [Lean Language Reference](https://lean-lang.org/doc/reference/latest/)), follows links on that exact official host, extracts titles/headings/text, and stores a JSON cache. `docs_index.py` searches cached pages with weighted token overlap. `term_analyzer.py` creates coverage records for every word and general 2/3-word phrases. `agent.py` loads `SKILL.md` at startup and enforces the retrieval-before-generation order.

The crawler is deliberately bounded by `--max-pages` and never leaves the configured official host. Refreshing is opt-in; normal runs reuse the cache.

## Run

```bash
pip install -r requirements.txt
python main.py
```

For one query:

```bash
python main.py --query "What is an inductive type in Lean?"
python main.py --debug --query "What is an inductive type in Lean?"
python main.py --refresh-docs --query "What is a theorem?"
```

To annotate Lean code token by token, use `--annotate` and pass the snippet with `--code`:

```bash
python main.py --annotate --cache /private/tmp/lean-doc-inductive.json \
  --code $'theorem foo (n : Nat) : n + 0 = n := by\n  simp'
```

This produces labels such as `theorem → keyword`, `foo → identifier`, `:= → syntax`, `= → notation`, and `simp → tactic identifier`. Each token is sent through the documentation search layer before its label is emitted.

For the full manager workflow—line-by-line categories, documentation context for each extracted thing, and an English translation—use `--explain-code`:

```bash
python main.py --explain-code --debug \
  --cache /private/tmp/lean-doc-inductive.json \
  --code $'theorem foo (n : Nat) : n + 0 = n := by\n  simp'
```

The optional LLM provider receives the code only after documentation context has been collected. Without `OPENAI_API_KEY`, the prototype uses a deterministic English explanation based on the parsed declaration.

The first run may download pages. Later runs use `.lean-doc-cache.json`. Change the source or cache with `--base-url` and `--cache`, or the environment variables `LEAN_DOCS_BASE_URL` and `LEAN_DOCS_CACHE`.

## Tests

```bash
pytest
```

The tests use deterministic in-memory documentation fixtures and verify search, word/phrase coverage, ambiguity retries, source preservation, skill loading, offline behavior, cache reuse, and the no-key extractive path.
