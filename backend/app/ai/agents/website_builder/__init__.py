"""Agentic Website Builder — LangGraph multi-stage website generation.

Lean agent set (unnecessary agents removed / merged):

1. Parser        — structured requirements + feature checklist
2. Planner       — task graph + optional public GitHub inspiration
3. Images        — conditional asset resolution (before page codegen)
4. Scaffold      — foundation (Vite/Tailwind/entry) — Part 1A style
5. Home          — level-1 homepage (rich, feature-complete)
6. Level2        — second-level nav pages (catalogue / list / etc.)
7. Compiler      — deterministic Live Preview integrity check
8. Repair        — LLM repair loop (conditional on compiler failures)
9. PreviewGate   — signal Live Preview ready after L1+L2 (not an LLM)
10. Level3       — detail/third-level pages (runs after preview gate)
11. Validate     — assert every user-requested feature is present

Removed as separate agents:
- Dedicated "Show Live Preview" LLM agent → PreviewGate emits progress;
  the existing frontend Live Preview already renders applied files.
- Dedicated GitHub scrape agent → folded into Planner.
"""

from app.ai.agents.website_builder.runner import WebsiteBuilderRunner

__all__ = ["WebsiteBuilderRunner"]
