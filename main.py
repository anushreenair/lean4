"""Interactive entry point for the Lean documentation-first agent."""

# argparse keeps the script usable from a terminal, in a demo, or from a shell script.
import argparse
from pathlib import Path

from agent import DocumentationFirstAgent
from code_annotator import LeanCodeAnnotator
from code_understanding import DocumentationFirstCodeAgent, code_translator_from_environment
from config import Config
from docs_index import DocumentIndex
from docs_loader import DocumentationCrawler, DocumentationUnavailable, JsonDocumentCache
from llm import provider_from_environment


def build_agent(args) -> DocumentationFirstAgent:
    # All modes share the same configuration so they search the same official source.
    config = Config(
        base_url=args.base_url,
        cache_path=Path(args.cache),
        max_pages=args.max_pages,
    )
    cache = JsonDocumentCache(config.cache_path)
    # Reusing the cache avoids downloading the same documentation for every question.
    documents = DocumentationCrawler(config, cache).load(refresh=args.refresh_docs)
    return DocumentationFirstAgent(
        DocumentIndex(documents), provider_from_environment(), Path(__file__).with_name("SKILL.md")
    )


def build_annotator(args) -> LeanCodeAnnotator:
    # The token annotator uses the same cached index as the question-answering mode.
    config = Config(
        base_url=args.base_url,
        cache_path=Path(args.cache),
        max_pages=args.max_pages,
    )
    documents = DocumentationCrawler(config, JsonDocumentCache(config.cache_path)).load(
        refresh=args.refresh_docs
    )
    return LeanCodeAnnotator(DocumentIndex(documents), Path(__file__).with_name("SKILL.md"))


def build_code_agent(args) -> DocumentationFirstCodeAgent:
    # Code explanation needs both documentation search and a translator.
    config = Config(
        base_url=args.base_url,
        cache_path=Path(args.cache),
        max_pages=args.max_pages,
    )
    documents = DocumentationCrawler(config, JsonDocumentCache(config.cache_path)).load(
        refresh=args.refresh_docs
    )
    return DocumentationFirstCodeAgent(
        DocumentIndex(documents), code_translator_from_environment(), Path(__file__).with_name("SKILL.md")
    )


def print_answer(result, debug: bool = False) -> None:
    if debug:
        # Debug output makes the documentation-first process visible during development.
        print("\nQUERY")
        print(result.query)
        print("\nWORDS CHECKED")
        for item in result.coverage.words:
            marker = "✓" if item.checked else "✗"
            found = " (Lean result)" if item.result_found else ""
            print(f"{marker} {item.term}{found}")
        print("\nPHRASES CHECKED")
        for item in result.coverage.phrases:
            marker = "✓" if item.checked else "✗"
            found = " (Lean result)" if item.result_found else ""
            print(f"{marker} {item.term}{found}")
        print("\nDOCUMENTATION SEARCHED")
        for query in result.searches:
            print(f"- {query}")
    print("\nANSWER")
    print(result.answer)
    print("\nSOURCES")
    if result.sources:
        for number, source in enumerate(result.sources, 1):
            print(f"{number}. {source.title} — {source.url}")
    else:
        print("No documentation source was retrieved.")
    if result.fallback_reason:
        print(f"\nNOTE: {result.fallback_reason}")


def print_annotation(result, debug: bool = False) -> None:
    # Token output is kept separate from the richer English explanation output.
    print("\nTOKEN ANNOTATION")
    for token in result.tokens:
        print(f"{token.text} → {token.category}")
    if debug:
        print("\nDOCUMENTATION CHECKED BEFORE CLASSIFICATION")
        print(f"Tokens checked: {len(result.tokens)}")
        print("\nDOCUMENTATION SEARCHED")
        for query in result.searches:
            print(f"- {query}")
        print("\nSOURCES")
        for number, source in enumerate(result.sources, 1):
            print(f"{number}. {source}")


def print_code_explanation(result, debug: bool = False) -> None:
    # These sections mirror the requested workflow: breakdown, context, translation, sources.
    print("\nCODE BREAKDOWN")
    for thing in result.things:
        print(f"line {thing.line}: {thing.text} → {thing.category}")
    print("\nDOCUMENTATION CONTEXT")
    if result.context:
        for context_line in result.context.splitlines():
            print(f"- {context_line}")
    else:
        print("No matching cached documentation context was found.")
    if debug:
        print("\nDOCUMENTATION SEARCHED BEFORE TRANSLATION")
        for query in result.searches:
            print(f"- {query}")
    print("\nENGLISH TRANSLATION")
    print(result.english)
    print("\nSOURCES")
    if result.sources:
        for number, source in enumerate(result.sources, 1):
            print(f"{number}. {source}")
    else:
        print("No documentation sources were retrieved.")


def parse_args():
    # Explicit modes keep one command useful for both questions and pasted Lean code.
    parser = argparse.ArgumentParser(description="Lean Documentation Agent")
    parser.add_argument("--debug", action="store_true", help="show word/phrase coverage and searches")
    parser.add_argument("--refresh-docs", action="store_true", help="re-crawl official documentation")
    parser.add_argument("--query", help="answer one query and exit")
    parser.add_argument("--annotate", action="store_true", help="annotate Lean code token by token")
    parser.add_argument("--explain-code", action="store_true", help="document and translate Lean code")
    parser.add_argument("--code", help="Lean code to annotate; use $'...' for multiple lines")
    parser.add_argument("--base-url", default=Config().base_url, help="official docs root URL")
    parser.add_argument("--cache", default=str(Config().cache_path), help="local JSON cache path")
    parser.add_argument("--max-pages", type=int, default=Config().max_pages, help="crawler page limit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("Lean Documentation Agent")
    try:
        # Code modes are handled first because they need a different result formatter.
        if args.explain_code:
            code_agent = build_code_agent(args)
            code = args.code
            if code is None:
                code = input("Paste Lean code to explain:\n> ")
            print_code_explanation(code_agent.explain(code), args.debug)
            return 0
        if args.annotate:
            annotator = build_annotator(args)
            code = args.code
            if code is None:
                code = input("Paste Lean code to annotate:\n> ")
            print_annotation(annotator.annotate(code), args.debug)
            return 0
        agent = build_agent(args)
    except DocumentationUnavailable as exc:
        # A clear message is more useful than a traceback when the docs/cache is unavailable.
        print(f"Documentation unavailable: {exc}")
        print("Connect to the internet or provide an existing cache with --cache.")
        return 2

    if args.query:
        print_answer(agent.answer(args.query), args.debug)
        return 0
    while True:
        try:
            query = input("\nAsk a question (or press Enter to quit):\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not query:
            return 0
        print_answer(agent.answer(query), args.debug)


if __name__ == "__main__":
    raise SystemExit(main())
