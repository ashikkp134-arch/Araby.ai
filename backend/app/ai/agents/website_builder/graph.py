"""LangGraph wiring for the agentic website builder.

Home-first flow (what the user sees first):

  START → parse → plan → (images?) → home_foundation → home_page
        → compile_home → [repair ⟲] → cache_home → preview_gate
        → level2 → compile_l2 → [repair ⟲]
        → level3 → compile_l3 → [repair ⟲]
        → validate → notify_done → END

Live Preview opens as soon as the production Home page compiles.
Level-2 / Level-3 continue in the background using the cached Home code
as the style/routing reference.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.ai.agents.website_builder.nodes.codegen import (
    cache_home_node,
    home_foundation_node,
    home_page_node,
    level2_node,
    level3_node,
)
from app.ai.agents.website_builder.nodes.compiler import (
    compile_node,
    notify_done_node,
    preview_gate_node,
    repair_node,
    validate_node,
)
from app.ai.agents.website_builder.nodes.images import images_node
from app.ai.agents.website_builder.nodes.parser import parse_node
from app.ai.agents.website_builder.nodes.planner import plan_node
from app.ai.agents.website_builder.state import WebsiteBuilderState


def _after_plan(state: WebsiteBuilderState) -> Literal["images", "home_foundation"]:
    if state.get("needs_images", True):
        return "images"
    return "home_foundation"


def _after_compile_home(
    state: WebsiteBuilderState,
) -> Literal["repair_home", "cache_home"]:
    report = state.get("compile_report")
    repair_count = int(state.get("repair_count") or 0)
    max_repair = int(state.get("max_repair") or 2)
    if report and not report.ok and repair_count < max_repair:
        return "repair_home"
    return "cache_home"


def _after_compile_level2(
    state: WebsiteBuilderState,
) -> Literal["repair_level2", "level3"]:
    report = state.get("compile_report")
    repair_count = int(state.get("repair_count") or 0)
    max_repair = int(state.get("max_repair") or 2)
    if report and not report.ok and repair_count < max_repair:
        return "repair_level2"
    return "level3"


def _after_compile_level3(
    state: WebsiteBuilderState,
) -> Literal["repair_level3", "validate"]:
    report = state.get("compile_report")
    repair_count = int(state.get("repair_count") or 0)
    max_repair = int(state.get("max_repair") or 2)
    if report and not report.ok and repair_count < max_repair:
        return "repair_level3"
    return "validate"


def build_website_graph():
    """Compile the website-builder StateGraph."""
    graph = StateGraph(WebsiteBuilderState)

    graph.add_node("parse", parse_node)
    graph.add_node("plan", plan_node)
    graph.add_node("images", images_node)
    graph.add_node("home_foundation", home_foundation_node)
    graph.add_node("home_page", home_page_node)
    graph.add_node("compile_home", compile_node)
    graph.add_node("repair_home", repair_node)
    graph.add_node("cache_home", cache_home_node)
    graph.add_node("preview_gate", preview_gate_node)
    graph.add_node("level2", level2_node)
    graph.add_node("compile_level2", compile_node)
    graph.add_node("repair_level2", repair_node)
    graph.add_node("level3", level3_node)
    graph.add_node("compile_level3", compile_node)
    graph.add_node("repair_level3", repair_node)
    graph.add_node("validate", validate_node)
    graph.add_node("notify_done", notify_done_node)

    graph.add_edge(START, "parse")
    graph.add_edge("parse", "plan")
    graph.add_conditional_edges(
        "plan",
        _after_plan,
        {"images": "images", "home_foundation": "home_foundation"},
    )
    graph.add_edge("images", "home_foundation")
    graph.add_edge("home_foundation", "home_page")
    graph.add_edge("home_page", "compile_home")
    graph.add_conditional_edges(
        "compile_home",
        _after_compile_home,
        {"repair_home": "repair_home", "cache_home": "cache_home"},
    )
    graph.add_edge("repair_home", "compile_home")
    # Home is production-ready → open Live Preview, then continue L2/L3.
    graph.add_edge("cache_home", "preview_gate")
    graph.add_edge("preview_gate", "level2")
    graph.add_edge("level2", "compile_level2")
    graph.add_conditional_edges(
        "compile_level2",
        _after_compile_level2,
        {"repair_level2": "repair_level2", "level3": "level3"},
    )
    graph.add_edge("repair_level2", "compile_level2")
    graph.add_edge("level3", "compile_level3")
    graph.add_conditional_edges(
        "compile_level3",
        _after_compile_level3,
        {"repair_level3": "repair_level3", "validate": "validate"},
    )
    graph.add_edge("repair_level3", "compile_level3")
    graph.add_edge("validate", "notify_done")
    graph.add_edge("notify_done", END)

    return graph.compile()
