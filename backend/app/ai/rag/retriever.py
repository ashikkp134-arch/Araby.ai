"""Lightweight RAG helpers for future retrieval expansion."""

from typing import Any, Dict, List


def rank_files_by_query(files: List[Dict[str, Any]], query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Rank files with a simple keyword overlap heuristic.

    Args:
        files: Project files.
        query: User query text.
        limit: Max files to return.

    Returns:
        Ranked file documents.
    """
    terms = {term.lower() for term in query.split() if len(term) > 2}
    if not terms:
        return files[:limit]

    def score(file_doc: Dict[str, Any]) -> int:
        haystack = f"{file_doc.get('path', '')}\n{file_doc.get('content', '')}".lower()
        return sum(1 for term in terms if term in haystack)

    ranked = sorted(files, key=score, reverse=True)
    return [item for item in ranked if score(item) > 0][:limit] or files[:limit]
