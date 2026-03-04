"""Adaptive deep research workflow with dynamic re-planning."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse
from typing import Any, Optional

import json_repair

from gpt_researcher.llm_provider.generic.base import ReasoningEfforts
from gpt_researcher.orchestration import (
    BranchBudgetManager,
    EntropyTracker,
    ResearchTrace,
    SaliencyDetector,
    TaskNode,
    TaskStage,
    TaskStatus,
    build_default_task_graph,
    build_task_graph_from_outline,
    build_resolution_queries,
    detect_conflicts,
)
from gpt_researcher.orchestration.coverage_lenses import (
    assess_chain_coverage,
    assess_text_coverage,
    coverage_chain_prompt_block,
    coverage_lens_prompt_block,
    resolve_chain_steps,
)

from ..actions.query_processing import get_search_results
from ..utils.llm import create_chat_completion

logger = logging.getLogger(__name__)

# Keep context smaller than model max for predictable report generation.
MAX_CONTEXT_WORDS = 25000


def count_words(text: str | list[str]) -> int:
    if isinstance(text, list):
        text = " ".join(text)
    return len(str(text).split())


def trim_context_to_word_limit(context_list: list[str], max_words: int = MAX_CONTEXT_WORDS) -> list[str]:
    total_words = 0
    trimmed: list[str] = []
    for item in reversed(context_list):
        words = count_words(item)
        if total_words + words <= max_words:
            trimmed.insert(0, item)
            total_words += words
    return trimmed


@dataclass
class AdaptiveResearchProgress:
    current_depth: int
    total_depth: int
    current_breadth: int
    total_breadth: int
    current_query: Optional[str] = None
    completed_queries: int = 0
    total_queries: int = 0
    status: str = "researching"


class AdaptiveDeepResearchSkill:
    def __init__(self, researcher):
        self.researcher = researcher
        self.cfg = researcher.cfg
        self.websocket = researcher.websocket
        self.headers = researcher.headers or {}

        # Core controls
        self.breadth = getattr(self.cfg, "deep_research_breadth", 3)
        self.concurrency_limit = getattr(self.cfg, "deep_research_concurrency", 4)
        self.min_depth = getattr(self.cfg, "adaptive_min_depth", 1)
        self.max_depth = getattr(self.cfg, "adaptive_max_depth", 5)
        self.run_timeout_seconds = max(120, getattr(self.cfg, "adaptive_run_timeout_seconds", 1800))
        self.quality_threshold = getattr(self.cfg, "adaptive_quality_threshold", 7.5)
        self.search_timeout_seconds = getattr(self.cfg, "adaptive_search_timeout_seconds", 30)
        self.query_matrix_timeout_seconds = getattr(self.cfg, "adaptive_query_matrix_timeout_seconds", 25)
        self.claim_extraction_timeout_seconds = getattr(self.cfg, "adaptive_claim_extraction_timeout_seconds", 35)
        self.max_consecutive_empty_rounds = getattr(self.cfg, "adaptive_max_consecutive_empty_rounds", 2)
        self.max_conflicts_per_node = getattr(self.cfg, "adaptive_max_conflicts_per_node", 2)
        self.max_dimensions = max(3, getattr(self.cfg, "adaptive_max_dimensions", 8))
        self.source_quality_filter_enabled = getattr(self.cfg, "adaptive_source_quality_filter_enabled", True)
        self.max_sources_per_query = getattr(self.cfg, "adaptive_max_sources_per_query", 5)
        self.max_sources_per_domain = getattr(self.cfg, "adaptive_max_sources_per_domain", 2)
        self.min_source_quality_score = getattr(self.cfg, "adaptive_min_source_quality_score", 0.0)
        self.require_high_quality_source_quota = getattr(self.cfg, "adaptive_require_high_quality_source_quota", True)
        self.high_quality_source_quota = max(0.0, min(1.0, getattr(self.cfg, "adaptive_high_quality_source_quota", 0.5)))
        self.cache_enabled = getattr(self.cfg, "adaptive_cache_enabled", True)
        self.max_rounds_per_node = max(1, getattr(self.cfg, "adaptive_max_rounds_per_node", 2))
        self.max_queries_per_round = max(1, getattr(self.cfg, "adaptive_max_queries_per_round", self.breadth))
        self.max_query_failures_per_node = max(1, getattr(self.cfg, "adaptive_max_query_failures_per_node", 2))
        self.failure_rate_reduce_threshold = max(
            0.1, min(1.0, getattr(self.cfg, "adaptive_failure_rate_reduce_threshold", 0.67))
        )
        self.query_matrix_llm_disable_after_failures = max(
            1, getattr(self.cfg, "adaptive_query_matrix_llm_disable_after_failures", 2)
        )
        self.claim_llm_disable_after_failures = max(
            1, getattr(self.cfg, "adaptive_claim_llm_disable_after_failures", 3)
        )
        self.failed_domain_threshold = max(1, getattr(self.cfg, "adaptive_failed_domain_threshold", 2))
        self.min_completed_nodes_for_early_stop = max(1, getattr(self.cfg, "adaptive_min_completed_nodes_for_early_stop", 4))
        self.high_quality_domains = {
            str(d).lower().strip()
            for d in getattr(self.cfg, "adaptive_high_quality_domains", [])
            if str(d).strip()
        }
        self.low_quality_domains = {
            str(d).lower().strip()
            for d in getattr(self.cfg, "adaptive_low_quality_domains", [])
            if str(d).strip()
        }
        self.entropy_min_gain = getattr(self.cfg, "entropy_min_gain", 0.08)
        self.saliency_threshold = getattr(self.cfg, "saliency_threshold", 0.72)
        self.default_tavily_depth = getattr(self.cfg, "tavily_search_depth_default", "basic")
        self.tavily_advanced_enabled = getattr(self.cfg, "tavily_advanced_enabled", False)
        self.max_branch_queries = getattr(self.cfg, "rabbit_hole_max_queries_per_branch", 3)
        self.max_branches = getattr(self.cfg, "rabbit_hole_max_branches", 2)
        self.source_policy = str(getattr(researcher, "source_policy", "medium_tier") or "medium_tier").strip().lower()
        if self.source_policy not in {"strict_tier", "medium_tier", "broad_collect"}:
            self.source_policy = "medium_tier"
        self.coverage_enhancer_enabled = bool(getattr(self.cfg, "adaptive_coverage_enhancer_enabled", False))
        self.coverage_min_ratio = max(0.0, min(1.0, float(getattr(self.cfg, "adaptive_coverage_min_ratio", 0.75))))
        self.coverage_profile = str(getattr(self.cfg, "adaptive_coverage_profile", "balanced") or "balanced").strip().lower()
        if self.coverage_profile not in {"balanced", "high_coverage"}:
            self.coverage_profile = "balanced"
        self.chain_enforcer_enabled = bool(getattr(self.cfg, "adaptive_chain_enforcer_enabled", True))
        self.chain_min_ratio = max(0.0, min(1.0, float(getattr(self.cfg, "adaptive_chain_min_ratio", 0.90))))
        self.chain_require_explicit_sections = bool(
            getattr(self.cfg, "adaptive_chain_require_explicit_sections", True)
        )
        self.chain_profile_mode = str(getattr(self.cfg, "adaptive_chain_profile_mode", "dual") or "dual").strip().lower()
        if self.chain_profile_mode not in {"generic", "dual"}:
            self.chain_profile_mode = "dual"
        self.chain_industry_profile = str(
            getattr(self.cfg, "adaptive_chain_industry_profile", "auto") or "auto"
        ).strip().lower()
        self.chain_patch_max_rounds = max(1, int(getattr(self.cfg, "adaptive_chain_patch_max_rounds", 1)))
        self.chain_steps = resolve_chain_steps(
            profile_mode=self.chain_profile_mode,
            industry_profile=self.chain_industry_profile,
            query=str(getattr(self.researcher, "query", "") or ""),
        )

        self.entropy_tracker = EntropyTracker(min_gain=self.entropy_min_gain, patience=2)
        self.saliency_detector = SaliencyDetector(self.saliency_threshold)
        self.budget_manager = BranchBudgetManager(self.max_branches, self.max_branch_queries)
        self.trace = ResearchTrace()
        self.locked_outline = getattr(researcher, "research_outline", None) or None
        self.report_blueprint = getattr(researcher, "report_blueprint", None) or None
        self.user_requirements = getattr(researcher, "user_requirements", None) or None

        # Long-range memory structures
        self.evidence_store: list[dict[str, Any]] = []
        self.research_journal: dict[str, list[str]] = {
            "facts": [],
            "contradictions": [],
            "hypotheses": [],
            "pending": [],
        }
        self.claim_to_anchors: dict[str, list[dict[str, Any]]] = {}
        self.learned_claims_by_node: dict[str, set[str]] = {}
        self.global_claims: list[str] = []
        self.completed_queries = 0
        self.total_queries = 0
        self.search_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.scrape_cache: dict[str, str] = {}
        self.claim_cache: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
        self.node_seen_queries: dict[str, set[str]] = {}
        self._node_runtime_flags: dict[str, set[str]] = {}
        self.node_failure_stats: dict[str, dict[str, int]] = {}
        self._node_chain_low_hit_streak: dict[str, int] = {}
        self._covered_chain_step_ids: set[str] = set()
        self.failed_domains: Counter[str] = Counter()
        self.blocked_domains: set[str] = set()
        self.claim_ledger: list[dict[str, Any]] = []
        self.diagnostics: dict[str, Any] = {
            "dimension_planning_fallbacks": 0,
            "query_matrix_fallbacks": 0,
            "claim_extraction_fallbacks": 0,
            "search_failures": 0,
            "scraper_failures": 0,
            "empty_round_stops": 0,
            "repeated_failure_stops": 0,
            "blocked_domains": 0,
            "run_timeout_stops": 0,
            "coverage_ratio": 0.0,
            "coverage_missing_lenses_count": 0,
            "coverage_missing_lenses": [],
            "chain_coverage_ratio": 0.0,
            "chain_missing_steps_count": 0,
            "chain_missing_steps": [],
            "chain_step_query_coverage": [],
        }

    async def run(self, on_progress=None) -> str:
        start_time = time.time()
        deadline_ts = start_time + self.run_timeout_seconds if self.run_timeout_seconds > 0 else None

        dimensions: list[str] = []
        if self.locked_outline and isinstance(self.locked_outline, dict):
            graph = build_task_graph_from_outline(self.locked_outline)
            dimensions = [str(section.get("title") or section.get("intent") or "") for section in (self.locked_outline.get("sections") or [])]
        else:
            dimensions = await self._plan_dimensions(self.researcher.query)
            graph = build_default_task_graph(self.researcher.query, dimensions)

        if not graph.nodes:
            dimensions = await self._plan_dimensions(self.researcher.query)
            graph = build_default_task_graph(self.researcher.query, dimensions)

        coverage = assess_text_coverage(dimensions or [])
        self.diagnostics["coverage_ratio"] = coverage.get("ratio", 0.0)
        self.diagnostics["coverage_missing_lenses_count"] = len(coverage.get("missing_ids") or [])
        self.diagnostics["coverage_missing_lenses"] = list(coverage.get("missing_labels") or [])
        chain_coverage = assess_chain_coverage(dimensions or [], chain_steps=self.chain_steps)
        self.diagnostics["chain_coverage_ratio"] = chain_coverage.get("ratio", 0.0)
        self.diagnostics["chain_missing_steps_count"] = len(chain_coverage.get("missing_ids") or [])
        self.diagnostics["chain_missing_steps"] = list(chain_coverage.get("missing_labels") or [])

        if isinstance(self.locked_outline, dict):
            self.trace.set_outline(self.locked_outline)
        if isinstance(self.report_blueprint, dict):
            self.trace.set_blueprint(self.report_blueprint)
        self.trace.set_planner(graph.export_state())

        depth_count = 0
        progress = AdaptiveResearchProgress(
            current_depth=0,
            total_depth=self.max_depth,
            current_breadth=0,
            total_breadth=self.breadth,
            completed_queries=0,
            total_queries=0,
            status="planning",
        )

        while graph.has_pending() and depth_count < self.max_depth:
            if deadline_ts is not None and time.time() >= deadline_ts:
                self.diagnostics["run_timeout_stops"] += 1
                logger.warning("Adaptive deep research global timeout reached; stopping further node execution.")
                break
            ready = graph.get_ready_nodes(limit=1)
            if not ready:
                break
            node = ready[0]
            depth_count += 1
            graph.mark_status(node.node_id, TaskStatus.IN_PROGRESS)

            progress.current_depth = depth_count
            progress.status = "researching"
            progress.current_breadth = 0
            if on_progress:
                on_progress(progress)

            await self._process_node(node, depth_count, progress, graph, on_progress, deadline_ts=deadline_ts)
            node.metadata["termination_reason"] = node.metadata.get("termination_reason", "completed")
            node_stats = self.node_failure_stats.get(node.node_id, {})
            if node_stats:
                node.metadata["search_failures"] = node_stats.get("search_failures", 0)
                node.metadata["scrape_failures"] = node_stats.get("scrape_failures", 0)
            graph.mark_status(node.node_id, TaskStatus.COMPLETED)
            self.trace.set_planner(graph.export_state())

            if (
                depth_count >= self.min_depth
                and self._can_early_stop(graph)
                and self._estimate_quality_score() >= self.quality_threshold
            ):
                logger.info("Adaptive deep research stopped early: quality threshold reached.")
                break

        budget_snapshot = self.budget_manager.export()
        budget_snapshot["global_completed_queries"] = self.completed_queries
        self.trace.set_budget(budget_snapshot)
        self.diagnostics["blocked_domains"] = len(self.blocked_domains)
        self.trace.set_diagnostics(self.diagnostics.copy())
        self.claim_ledger = self._build_claim_ledger()
        failed_core_claims = [item for item in self.claim_ledger if not bool(item.get("policy_pass"))]
        if failed_core_claims:
            self.research_journal["pending"].append(
                f"{len(failed_core_claims)} core conclusions do not satisfy source policy `{self.source_policy}`."
            )
        self.trace.set_claim_ledger(self.claim_ledger)
        self.trace.set_citation_coverage(self._compute_citation_coverage())

        # Build final context
        final_context = self._build_final_context()
        final_context = trim_context_to_word_limit(final_context)

        self.researcher.context = "\n".join(final_context)
        self.researcher.research_trace = self.trace.to_dict()

        end_time = time.time()
        execution_time = timedelta(seconds=end_time - start_time)
        logger.info(f"Adaptive deep research completed in {execution_time}")
        logger.info(f"Adaptive deep research collected {len(self.researcher.visited_urls)} URLs")

        return self.researcher.context

    async def _process_node(
        self,
        node: TaskNode,
        depth_count: int,
        progress: AdaptiveResearchProgress,
        graph,
        on_progress=None,
        deadline_ts: float | None = None,
    ) -> str:
        rounds = 0
        termination_reason = "max_rounds"
        known_claims = self.learned_claims_by_node.get(node.node_id, set())
        branch_spawned = False
        consecutive_empty_rounds = 0
        consecutive_failed_rounds = 0
        max_rounds = max(self.min_depth, min(self.max_rounds_per_node, self.max_depth))
        seen_queries = self.node_seen_queries.setdefault(node.node_id, set())
        runtime_flags = self._node_runtime_flags.setdefault(node.node_id, set())
        node_stats = self.node_failure_stats.setdefault(
            node.node_id,
            {"search_failures": 0, "scrape_failures": 0},
        )

        while rounds < max_rounds:
            if deadline_ts is not None and time.time() >= deadline_ts:
                self.diagnostics["run_timeout_stops"] += 1
                termination_reason = "timeout"
                self.research_journal["pending"].append(
                    f"Node '{node.title}' stopped due to global run timeout."
                )
                break
            rounds += 1
            queries = await self._generate_query_matrix(node, rounds)
            if not queries:
                termination_reason = "no_queries"
                break
            deduped_queries: list[str] = []
            for query in queries:
                normalized = " ".join(query.lower().split())
                if normalized in seen_queries:
                    continue
                seen_queries.add(normalized)
                deduped_queries.append(query)
            round_query_limit = max(
                1,
                min(self.max_queries_per_round, self.breadth) - min(consecutive_failed_rounds, self.max_queries_per_round - 1),
            )
            queries = deduped_queries[:round_query_limit]
            if not queries:
                termination_reason = "no_new_queries"
                break

            self.total_queries += len(queries)
            progress.total_queries = self.total_queries
            progress.total_breadth = len(queries)
            progress.current_breadth = 0

            semaphore = asyncio.Semaphore(self.concurrency_limit)

            async def process_query(query: str):
                async with semaphore:
                    progress.current_query = query
                    progress.current_breadth += 1
                    if on_progress:
                        on_progress(progress)
                    return await self._collect_claims_for_query(node, query)

            results = await asyncio.gather(*[process_query(q) for q in queries], return_exceptions=True)

            round_claims: list[str] = []
            round_claim_records: list[tuple[str, str | None]] = []
            failed_results = 0
            for result in results:
                if isinstance(result, Exception) or not result:
                    failed_results += 1
                    continue
                claims, claim_urls = result
                round_claims.extend(claims)
                round_claim_records.extend(claim_urls)

            metrics = self.entropy_tracker.evaluate(node.node_id, round_claims, known_claims)
            self.trace.add_loop_metric(
                {
                    "node_id": node.node_id,
                    "node_title": node.title,
                    "round": rounds,
                    "novelty_score": metrics.novelty_score,
                    "redundancy_score": metrics.redundancy_score,
                    "entropy_gain": metrics.entropy_gain,
                }
            )

            for claim in round_claims:
                normalized = claim.lower().strip()
                if normalized and normalized not in known_claims:
                    known_claims.add(normalized)
                    self.global_claims.append(claim)
                    self.research_journal["facts"].append(claim)

            if round_claim_records and not branch_spawned:
                branch_spawned = self._evaluate_and_maybe_replan(node, round_claim_records, graph)

            conflicts = detect_conflicts(round_claims)[: self.max_conflicts_per_node]
            if conflicts:
                await self._resolve_conflicts(conflicts, node)

            if round_claims:
                consecutive_empty_rounds = 0
            else:
                consecutive_empty_rounds += 1
                if consecutive_empty_rounds >= self.max_consecutive_empty_rounds:
                    self.diagnostics["empty_round_stops"] += 1
                    termination_reason = "empty_rounds"
                    self.research_journal["pending"].append(
                        f"Node '{node.title}' stopped after {consecutive_empty_rounds} empty rounds."
                    )
                    break

            failure_ratio = failed_results / max(1, len(results))
            if failed_results == len(results) or (failure_ratio >= self.failure_rate_reduce_threshold and not round_claims):
                consecutive_failed_rounds += 1
            else:
                consecutive_failed_rounds = 0

            if "budget" in runtime_flags and failed_results == len(results):
                termination_reason = "budget"
                break

            if consecutive_failed_rounds >= self.max_query_failures_per_node and rounds >= self.min_depth:
                self.diagnostics["repeated_failure_stops"] += 1
                termination_reason = "timeout" if "timeout" in runtime_flags else "query_failures"
                self.research_journal["pending"].append(
                    f"Node '{node.title}' stopped due to repeated query failures."
                )
                break

            # Keep running until at least min_depth; after that use saturation to stop.
            if rounds >= self.min_depth and (metrics.saturated or metrics.entropy_gain < self.entropy_min_gain):
                termination_reason = "entropy_stop"
                break

        self.learned_claims_by_node[node.node_id] = known_claims
        node.metadata["termination_reason"] = termination_reason
        node.metadata["executed_rounds"] = rounds
        node.metadata["search_failures"] = node_stats.get("search_failures", 0)
        node.metadata["scrape_failures"] = node_stats.get("scrape_failures", 0)
        return termination_reason

    async def _collect_claims_for_query(self, node: TaskNode, query: str) -> tuple[list[str], list[tuple[str, str | None]]]:
        if not self.budget_manager.consume_query(
            node.node_id,
            is_branch=(node.branch_type == "rabbit_hole"),
        ):
            self._node_runtime_flags.setdefault(node.node_id, set()).add("budget")
            node.metadata["termination_reason"] = "budget"
            self.research_journal["pending"].append(
                f"Rabbit-hole budget exhausted for node '{node.title}'."
            )
            return [], []

        context_text, urls = await self._collect_query_context(node, query)
        self.completed_queries += 1

        if not context_text.strip() or context_text.startswith("No high-quality context extracted"):
            return [], []

        claims_with_urls = await self._extract_claims(query, context_text, urls, node_id=node.node_id)
        claims: list[str] = []
        claim_url_pairs: list[tuple[str, str | None]] = []
        for claim, url in claims_with_urls:
            claims.append(claim)
            claim_url_pairs.append((claim, url))
            anchor = self._build_anchor(claim=claim, url=url, query=query, node=node)
            self.claim_to_anchors.setdefault(claim, []).append(anchor)
            self.trace.add_citation(claim, anchor)

        return claims, claim_url_pairs

    async def _collect_query_context(self, node: TaskNode, query: str) -> tuple[str, list[str]]:
        has_conflict_pressure = bool(self.research_journal["contradictions"])
        search_depth = self._resolve_search_depth(node, has_conflict_pressure)

        retriever = self.researcher.retrievers[0]
        original_headers = self.researcher.headers
        self.researcher.headers = dict(self.researcher.headers or {})
        self.researcher.headers["tavily_search_depth"] = search_depth
        if search_depth == "advanced":
            self.researcher.headers["tavily_include_raw_content"] = "true"

        cache_key = (query.strip().lower(), search_depth)
        search_results: list[dict[str, Any]] = []
        if self.cache_enabled and cache_key in self.search_cache:
            search_results = list(self.search_cache[cache_key])

        try:
            if not search_results:
                search_results = await asyncio.wait_for(
                    get_search_results(
                        query=query,
                        retriever=retriever,
                        query_domains=self.researcher.query_domains,
                        researcher=self.researcher,
                    ),
                    timeout=self.search_timeout_seconds,
                )
        except Exception as exc:
            self.diagnostics["search_failures"] += 1
            node_stats = self.node_failure_stats.setdefault(
                node.node_id,
                {"search_failures": 0, "scrape_failures": 0},
            )
            node_stats["search_failures"] += 1
            if isinstance(exc, asyncio.TimeoutError):
                self._node_runtime_flags.setdefault(node.node_id, set()).add("timeout")
            logger.warning(f"Search failed for query '{query}': {exc}")
            search_results = []
        finally:
            self.researcher.headers = original_headers

        search_results = self._rank_and_filter_search_results(search_results)
        if self.cache_enabled and search_results:
            self.search_cache[cache_key] = list(search_results)

        urls: list[str] = []
        context_chunks: list[str] = []
        synthetic_sources: list[dict[str, Any]] = []
        for result in search_results:
            url = result.get("href") or result.get("url")
            domain = self._domain_from_url(str(url or ""))
            if domain and domain in self.blocked_domains:
                continue
            body = result.get("raw_content") or result.get("body") or result.get("content")
            title = result.get("title", "")
            if url:
                urls.append(url)
                self.researcher.visited_urls.add(url)
            if body:
                context_chunks.append(str(body))
            if url and body:
                synthetic_sources.append({"url": url, "raw_content": body, "title": title, "image_urls": []})

        if synthetic_sources:
            self.researcher.add_research_sources(synthetic_sources)

        # If we still have low context density, fall back to scraper for new URLs.
        if count_words(context_chunks) < 220 and urls:
            urls_to_scrape = [
                u
                for u in urls[: self.cfg.max_search_results_per_query]
                if u and self._domain_from_url(u) not in self.blocked_domains
            ]
            cached_urls = []
            uncached_urls = []
            if self.cache_enabled:
                for url in urls_to_scrape:
                    if url in self.scrape_cache:
                        cached_urls.append(url)
                    else:
                        uncached_urls.append(url)
            else:
                uncached_urls = urls_to_scrape

            for url in cached_urls:
                cached_content = self.scrape_cache.get(url, "")
                if cached_content:
                    context_chunks.append(cached_content)

            try:
                if uncached_urls:
                    scraped_content = await asyncio.wait_for(
                        self.researcher.scraper_manager.browse_urls(uncached_urls),
                        timeout=self.search_timeout_seconds,
                    )
                    for item in scraped_content:
                        raw = item.get("raw_content")
                        src_url = item.get("url")
                        if raw:
                            context_chunks.append(raw)
                            if self.cache_enabled and src_url:
                                self.scrape_cache[str(src_url)] = str(raw)
            except Exception as exc:
                self.diagnostics["scraper_failures"] += 1
                node_stats = self.node_failure_stats.setdefault(
                    node.node_id,
                    {"search_failures": 0, "scrape_failures": 0},
                )
                node_stats["scrape_failures"] += 1
                for raw_url in uncached_urls:
                    domain = self._domain_from_url(raw_url)
                    if not domain:
                        continue
                    self.failed_domains[domain] += 1
                    if self.failed_domains[domain] >= self.failed_domain_threshold:
                        self.blocked_domains.add(domain)
                if isinstance(exc, asyncio.TimeoutError):
                    self._node_runtime_flags.setdefault(node.node_id, set()).add("timeout")
                logger.warning(f"Scraper fallback failed for query '{query}': {exc}")

        if not context_chunks:
            context_chunks.append(f"No high-quality context extracted for query: {query}")

        # Keep contexts compact per query.
        compact_context = " ".join(context_chunks)
        compact_context = compact_context[:16000]
        return compact_context, urls

    def _resolve_search_depth(self, node: TaskNode, has_conflict: bool) -> str:
        if not self.tavily_advanced_enabled:
            return self.default_tavily_depth
        if has_conflict or node.uncertainty >= 0.65:
            return "advanced"
        return self.default_tavily_depth

    def _can_early_stop(self, graph) -> bool:
        completed_nodes = [
            node for node in graph.nodes.values()
            if node.status == TaskStatus.COMPLETED
        ]
        if len(completed_nodes) < self.min_completed_nodes_for_early_stop:
            return False
        stages = {node.stage for node in completed_nodes}
        return TaskStage.FOUNDATION in stages and TaskStage.EVIDENCE in stages

    @staticmethod
    def _domain_from_url(url: str) -> str:
        try:
            return (urlparse(url).netloc or "").lower()
        except Exception:
            return ""

    def _is_high_quality_domain(self, domain: str) -> bool:
        if not domain:
            return False
        if domain in self.high_quality_domains:
            return True
        if domain.endswith(".gov"):
            return True
        return False

    def _score_source(self, result: dict[str, Any]) -> float:
        url = str(result.get("href") or result.get("url") or "").strip()
        title = str(result.get("title") or "").lower()
        body = str(result.get("body") or result.get("content") or result.get("raw_content") or "").lower()
        domain = self._domain_from_url(url)

        score = 0.0
        if domain in self.high_quality_domains:
            score += 3.0
        if domain in self.low_quality_domains:
            score -= 3.0

        if domain.endswith(".gov"):
            score += 2.0
        elif domain.endswith(".edu"):
            score += 1.5
        elif domain.endswith(".org"):
            score += 0.8

        authority_keywords = ("investor", "10-k", "sec filing", "earnings", "press release", "transcript")
        if any(k in title for k in authority_keywords):
            score += 0.8
        if any(k in body[:1200] for k in ("revenue", "gross margin", "operating margin", "guidance")):
            score += 0.4

        noise_keywords = ("shopping", "coupon", "affiliate", "sponsored")
        if any(k in body[:800] for k in noise_keywords):
            score -= 0.8
        if body and len(body) < 100:
            score -= 0.5
        return score

    def _rank_and_filter_search_results(self, search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not search_results:
            return []
        if not self.source_quality_filter_enabled:
            return search_results[: self.max_sources_per_query]

        scored: list[tuple[float, dict[str, Any]]] = []
        for result in search_results:
            url = str(result.get("href") or result.get("url") or "").strip()
            domain = self._domain_from_url(url)
            if domain and domain in self.blocked_domains:
                continue
            score = self._score_source(result)
            if score < self.min_source_quality_score:
                continue
            scored.append((score, result))

        if not scored:
            # If all got filtered out, keep original top results to avoid dead branch.
            return search_results[: self.max_sources_per_query]

        scored.sort(key=lambda item: item[0], reverse=True)

        required_hq = 0
        if self.require_high_quality_source_quota:
            required_hq = max(1, math.ceil(self.max_sources_per_query * self.high_quality_source_quota))

        domain_counter: Counter[str] = Counter()
        selected: list[dict[str, Any]] = []
        selected_keys: set[tuple[str, str]] = set()

        if required_hq > 0:
            for score, result in scored:
                url = str(result.get("href") or result.get("url") or "")
                domain = self._domain_from_url(url)
                if not self._is_high_quality_domain(domain):
                    continue
                if domain and domain_counter[domain] >= self.max_sources_per_domain:
                    continue
                selected.append(result)
                selected_keys.add((url, str(result.get("title") or "")))
                if domain:
                    domain_counter[domain] += 1
                if len(selected) >= min(required_hq, self.max_sources_per_query):
                    break

        domain_counter: Counter[str] = Counter()
        for item in selected:
            d = self._domain_from_url(str(item.get("href") or item.get("url") or ""))
            if d:
                domain_counter[d] += 1
        for score, result in scored:
            url = str(result.get("href") or result.get("url") or "")
            domain = self._domain_from_url(url)
            if (url, str(result.get("title") or "")) in selected_keys:
                continue
            if domain and domain_counter[domain] >= self.max_sources_per_domain:
                continue
            selected.append(result)
            selected_keys.add((url, str(result.get("title") or "")))
            if domain:
                domain_counter[domain] += 1
            if len(selected) >= self.max_sources_per_query:
                break

        selected = self._apply_low_quality_downsampling(selected, search_results)
        return selected if selected else search_results[: self.max_sources_per_query]

    def _apply_low_quality_downsampling(
        self,
        selected: list[dict[str, Any]],
        fallback_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not selected:
            return selected
        if self.source_policy == "broad_collect":
            return selected

        total = len(selected)
        if self.source_policy == "strict_tier":
            max_low_quality = 0
        else:
            max_low_quality = max(1, math.floor(total * 0.35))

        low_quality_seen = 0
        filtered: list[dict[str, Any]] = []
        for result in selected:
            url = str(result.get("href") or result.get("url") or "")
            domain = self._domain_from_url(url)
            is_low_quality = bool(domain and domain in self.low_quality_domains)
            if is_low_quality:
                if low_quality_seen >= max_low_quality:
                    continue
                low_quality_seen += 1
            filtered.append(result)

        if filtered:
            return filtered[: self.max_sources_per_query]
        return fallback_results[: self.max_sources_per_query]

    async def _plan_dimensions(self, query: str) -> list[str]:
        if self.locked_outline and isinstance(self.locked_outline, dict):
            sections = self.locked_outline.get("sections") or []
            locked_dimensions = [
                " | ".join(
                    [
                        str(section.get("title") or "").strip(),
                        str(section.get("intent") or "").strip(),
                        " ".join(section.get("key_questions") or []) if isinstance(section.get("key_questions"), list) else "",
                    ]
                ).strip(" |")
                for section in sections
                if isinstance(section, dict)
            ]
            locked_dimensions = [item for item in locked_dimensions if item]
            if locked_dimensions:
                return locked_dimensions[: self.max_dimensions]

        dim_range = "8-12" if self.coverage_profile == "high_coverage" else "6-10"
        prompt = f"""
You are planning a research DAG. Create {dim_range} concise, orthogonal research dimensions for:
{query}

Coverage lenses to maximize breadth:
{coverage_lens_prompt_block()}

Coverage chain to preserve narrative completeness:
{coverage_chain_prompt_block(self.chain_steps)}

Requirements:
- Dimensions must be mutually distinct (avoid near-duplicate wording).
- Avoid single-angle plans (for example only technical or only market).
- Include both evidence collection and execution-oriented dimensions.
- Ensure the set can support this chain explicitly:
  industry -> brand -> demand -> material/input -> technology/process -> execution.
- Return a JSON list of strings only.
- Prefix each dimension with one stage tag, e.g.:
  [industry], [brand], [demand], [material], [technology], [execution].
"""
        try:
            if self.diagnostics["query_matrix_fallbacks"] >= self.query_matrix_llm_disable_after_failures:
                raise RuntimeError("query_matrix_llm_disabled_after_failures")
            response = await asyncio.wait_for(
                create_chat_completion(
                    model=self.cfg.strategic_llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    llm_provider=self.cfg.strategic_llm_provider,
                    reasoning_effort=ReasoningEfforts.Medium.value,
                    temperature=0.2,
                    llm_kwargs=self.cfg.llm_kwargs,
                ),
                timeout=self.query_matrix_timeout_seconds,
            )
            parsed = json_repair.loads(response)
            if isinstance(parsed, list) and parsed:
                return [str(item) for item in parsed][: self.max_dimensions]
        except Exception as exc:
            self.diagnostics["dimension_planning_fallbacks"] += 1
            logger.warning(f"Dimension planning fallback triggered: {exc}")

        fallback_dimensions = [
            f"[industry] Industry context and external trajectory for {query}",
            f"[brand] Brand/entity positioning and baseline for {query}",
            f"[demand] Demand and stakeholder signals for {query}",
            f"[material] Materials/inputs and upstream constraints for {query}",
            f"[technology] Technology/process pathways for {query}",
            f"[execution] Execution roadmap, pilot milestones, and next actions for {query}",
            f"[execution] Economics and operational feasibility for {query}",
            f"[execution] Risk, compliance, and uncertainty for {query}",
        ]
        return fallback_dimensions[: self.max_dimensions]

    async def _generate_query_matrix(self, node: TaskNode, round_index: int) -> list[str]:
        uncovered_steps = [step for step in self.chain_steps if str(step.get("id")) not in self._covered_chain_step_ids]
        uncovered_step_ids = [str(step.get("id")) for step in uncovered_steps if str(step.get("id"))]
        uncovered_step_labels = [str(step.get("label")) for step in uncovered_steps if str(step.get("label"))]
        min_required_uncovered_hits = min(3, len(uncovered_steps))
        prompt = f"""
Generate up to {self.breadth} search queries for this research node.
Node: {node.title}
Description: {node.description}
Round: {round_index}
Overall research objective: {self.researcher.query}

Use mixed query intents across:
- factual baseline and definitions
- comparative options and tradeoffs
- counter-evidence or conflicting claims
- economics and operational feasibility
- risk/compliance or policy constraints
- implementation examples and roadmap signals
- latest developments and source verification
- macro context signals, focal-target evidence, stakeholder demand, and supply/input constraints

Currently uncovered chain steps:
{", ".join(uncovered_step_labels) if uncovered_step_labels else "none"}

Do not output only one intent type.
Every query must remain explicitly tied to the overall research objective, not just the node title.
- The query set must cover at least {min_required_uncovered_hits} uncovered chain steps in this round (if uncovered steps remain).
Return a JSON list of strings only.
"""
        try:
            response = await asyncio.wait_for(
                create_chat_completion(
                    model=self.cfg.strategic_llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    llm_provider=self.cfg.strategic_llm_provider,
                    reasoning_effort=ReasoningEfforts.Medium.value,
                    temperature=0.3,
                    llm_kwargs=self.cfg.llm_kwargs,
                ),
                timeout=self.query_matrix_timeout_seconds,
            )
            parsed = json_repair.loads(response)
            if isinstance(parsed, list):
                cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                cleaned = cleaned[: self.breadth]
                self._record_chain_query_coverage(
                    node=node,
                    round_index=round_index,
                    queries=cleaned,
                    uncovered_step_ids=uncovered_step_ids,
                    min_required_uncovered_hits=min_required_uncovered_hits,
                    source="llm",
                )
                streak = self._node_chain_low_hit_streak.get(node.node_id, 0)
                if streak >= 2 and uncovered_step_labels:
                    return self._fallback_queries(node, missing_steps=uncovered_step_labels, reason="low_chain_hit")
                return cleaned
        except Exception as exc:
            self.diagnostics["query_matrix_fallbacks"] += 1
            logger.warning(f"Query matrix fallback triggered: {exc}")

        return self._fallback_queries(node, missing_steps=uncovered_step_labels, reason="llm_error")

    def _record_chain_query_coverage(
        self,
        *,
        node: TaskNode,
        round_index: int,
        queries: list[str],
        uncovered_step_ids: list[str],
        min_required_uncovered_hits: int,
        source: str,
    ) -> None:
        coverage_all = assess_chain_coverage(queries or [], chain_steps=self.chain_steps)
        covered_all_ids = set(coverage_all.get("covered_ids") or [])
        self._covered_chain_step_ids.update(covered_all_ids)

        target_steps = [step for step in self.chain_steps if str(step.get("id")) in set(uncovered_step_ids)]
        if target_steps:
            coverage_target = assess_chain_coverage(queries or [], chain_steps=target_steps)
            covered_target_ids = set(coverage_target.get("covered_ids") or [])
        else:
            covered_target_ids = set()

        target_hits = len(covered_target_ids)
        if min_required_uncovered_hits > 0 and target_hits < min_required_uncovered_hits:
            self._node_chain_low_hit_streak[node.node_id] = self._node_chain_low_hit_streak.get(node.node_id, 0) + 1
        else:
            self._node_chain_low_hit_streak[node.node_id] = 0

        self.diagnostics["chain_step_query_coverage"].append(
            {
                "node_id": node.node_id,
                "round": round_index,
                "source": source,
                "covered_chain_steps": sorted(list(covered_all_ids)),
                "target_uncovered_hits": target_hits,
                "required_uncovered_hits": min_required_uncovered_hits,
                "low_hit_streak": self._node_chain_low_hit_streak.get(node.node_id, 0),
                "query_count": len(queries or []),
            }
        )
        self.diagnostics["chain_coverage_ratio"] = coverage_all.get("ratio", self.diagnostics.get("chain_coverage_ratio", 0.0))
        self.diagnostics["chain_missing_steps"] = list(coverage_all.get("missing_labels") or [])
        self.diagnostics["chain_missing_steps_count"] = len(coverage_all.get("missing_ids") or [])

    def _fallback_queries(
        self,
        node: TaskNode,
        missing_steps: list[str] | None = None,
        reason: str = "fallback",
    ) -> list[str]:
        topic = str(self.researcher.query or "").strip()
        base_queries = [
            f"{topic} macro trends and latest baseline updates",
            f"{topic} {node.title} stakeholder demand and benchmark comparison",
            f"{topic} {node.title} supply chain constraints cost capacity and compliance risks",
            f"{topic} {node.title} implementation cases milestones and decision gates",
        ]
        gap_queries: list[str] = []
        for label in (missing_steps or [])[:4]:
            gap_queries.append(f"{topic} {node.title} {label} evidence and latest data")
            gap_queries.append(f"{topic} {label} benchmark and implementation case")

        composed = gap_queries + base_queries
        deduped: list[str] = []
        seen: set[str] = set()
        for query in composed:
            normalized = " ".join(query.lower().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(query)

        selected = deduped[: min(self.breadth, self.max_queries_per_round)]
        self._record_chain_query_coverage(
            node=node,
            round_index=-1,
            queries=selected,
            uncovered_step_ids=[],
            min_required_uncovered_hits=0,
            source=f"fallback:{reason}",
        )
        return selected

    async def _extract_claims(
        self,
        query: str,
        context: str,
        urls: list[str],
        node_id: str | None = None,
    ) -> list[tuple[str, str | None]]:
        if not context.strip():
            return []
        if count_words(context) < 40:
            return []
        cache_key = (
            query.strip().lower(),
            hashlib.sha1(f"{context[:10000]}|{'|'.join(urls[:5])}".encode("utf-8")).hexdigest(),
        )
        if self.cache_enabled and cache_key in self.claim_cache:
            return list(self.claim_cache[cache_key])

        prompt = f"""
Given research context for query "{query}", extract up to 5 atomic factual claims.
For each claim, attach one best source URL from this candidate list: {urls}

Return JSON list with:
[{{"claim": "...", "url": "..."}}]
"""
        try:
            if self.diagnostics["claim_extraction_fallbacks"] >= self.claim_llm_disable_after_failures:
                raise RuntimeError("claim_llm_disabled_after_failures")
            response = await asyncio.wait_for(
                create_chat_completion(
                    model=self.cfg.smart_llm_model,
                    messages=[{"role": "user", "content": f"{prompt}\n\nContext:\n{context[:14000]}"}],
                    llm_provider=self.cfg.smart_llm_provider,
                    reasoning_effort=ReasoningEfforts.Medium.value,
                    temperature=0.2,
                    llm_kwargs=self.cfg.llm_kwargs,
                ),
                timeout=self.claim_extraction_timeout_seconds,
            )
            parsed = json_repair.loads(response)
            if isinstance(parsed, list):
                claims: list[tuple[str, str | None]] = []
                for item in parsed:
                    claim = str(item.get("claim", "")).strip() if isinstance(item, dict) else ""
                    url = str(item.get("url", "")).strip() if isinstance(item, dict) else ""
                    if claim:
                        claims.append((claim, url or (urls[0] if urls else None)))
                if claims:
                    if self.cache_enabled:
                        self.claim_cache[cache_key] = list(claims[:5])
                    return claims[:5]
        except Exception as exc:
            self.diagnostics["claim_extraction_fallbacks"] += 1
            if node_id and isinstance(exc, asyncio.TimeoutError):
                self._node_runtime_flags.setdefault(node_id, set()).add("timeout")
            logger.warning(f"Claim extraction fallback triggered: {exc}")

        # Heuristic fallback
        fallback_claims: list[tuple[str, str | None]] = []
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", context) if len(s.strip()) > 50]
        for sentence in sentences[:3]:
            fallback_claims.append((sentence, urls[0] if urls else None))
        if self.cache_enabled:
            self.claim_cache[cache_key] = list(fallback_claims)
        return fallback_claims

    def _evaluate_and_maybe_replan(
        self,
        node: TaskNode,
        round_claim_records: list[tuple[str, str | None]],
        graph,
    ) -> bool:
        known_claims = {c.lower().strip() for c in self.claim_to_anchors.keys()}
        for claim, url in round_claim_records:
            is_salient, score = self.saliency_detector.is_salient(
                research_goal=self.researcher.query,
                finding=claim,
                known_claims=known_claims,
                source_url=url,
            )
            if not is_salient:
                continue
            if not self.budget_manager.can_spawn_branch():
                self.research_journal["pending"].append(
                    f"Salient lead ignored due to branch budget: {claim}"
                )
                return False
            branch_id = graph.add_branch_node(
                parent_node_id=node.node_id,
                title=f"Unexpected lead: {claim[:80]}",
                description=claim,
                priority=min(1.0, node.priority + 0.1),
                uncertainty=min(1.0, node.uncertainty + 0.1),
                metadata={"saliency_score": score},
            )
            if branch_id and self.budget_manager.register_branch(branch_id, parent_id=node.node_id):
                self.trace.add_replan(
                    {
                        "trigger_node": node.node_id,
                        "trigger_claim": claim,
                        "saliency_score": score,
                        "new_node": branch_id,
                    }
                )
                return True
        return False

    async def _resolve_conflicts(self, conflicts, node: TaskNode) -> None:
        for conflict in conflicts:
            self.research_journal["contradictions"].append(
                f"{conflict.claim_a} <-> {conflict.claim_b}"
            )
            self.trace.add_conflict(conflict.to_dict())

            queries = build_resolution_queries(conflict, self.researcher.query)
            for query in queries[:2]:
                context, urls = await self._collect_query_context(node, query)
                claims = await self._extract_claims(query, context, urls, node_id=node.node_id)
                if claims:
                    conflict.status = "evidence_collected"
                    self.trace.add_conflict(conflict.to_dict())
                    self.research_journal["facts"].extend([claim for claim, _ in claims[:2]])
                    break

    def _build_anchor(self, claim: str, url: str | None, query: str, node: TaskNode) -> dict[str, Any]:
        snippet = claim[:260]
        anchor_hash = hashlib.sha1(f"{url}|{snippet}".encode("utf-8")).hexdigest()[:16]
        source_tier = self._classify_source_tier(url)
        anchor = {
            "url": url or "",
            "query": query,
            "node_id": node.node_id,
            "snippet": snippet,
            "anchor_hash": anchor_hash,
            "source_tier": source_tier,
            "confidence": 0.7 if source_tier in {"T1", "T2"} else 0.5,
        }
        self.evidence_store.append({"claim": claim, **anchor})
        return anchor

    def _classify_source_tier(self, url: str | None) -> str:
        if not url:
            return "T3"
        domain = self._domain_from_url(url)
        high_signal_suffixes = (
            ".gov",
            ".edu",
            ".ac.",
            "doi.org",
            "arxiv.org",
            "patents.google.com",
            "wipo.int",
            "iso.org",
            "iec.ch",
            "astm.org",
            "sec.gov",
            "who.int",
            "oecd.org",
            "imf.org",
            "worldbank.org",
            "europa.eu",
        )
        if any(token in domain for token in high_signal_suffixes):
            return "T1"

        mainstream_tokens = (
            "reuters.com",
            "apnews.com",
            "bloomberg.com",
            "wsj.com",
            "ft.com",
            "bbc.com",
            "nytimes.com",
            "forbes.com",
            "techcrunch.com",
            "mckinsey.com",
            "gartner.com",
            "statista.com",
        )
        if any(token in domain for token in mainstream_tokens):
            return "T2"
        return "T3"

    def _build_claim_ledger(self) -> list[dict[str, Any]]:
        ledger: list[dict[str, Any]] = []
        conflict_claim_text = " ".join(self.research_journal["contradictions"]).lower()
        for claim, anchors in self.claim_to_anchors.items():
            tiers = [str(anchor.get("source_tier") or "T3") for anchor in anchors]
            tier_rank = {"T1": 3, "T2": 2, "T3": 1}
            best_tier = "T3"
            if tiers:
                best_tier = max(tiers, key=lambda item: tier_rank.get(item, 0))
            confidence = min(1.0, 0.45 + 0.12 * len(anchors) + (0.2 if best_tier in {"T1", "T2"} else 0.0))
            is_conflict = claim.lower() in conflict_claim_text
            conflict_status = "open" if is_conflict else "none"
            resolution_note = "Potential contradiction detected and requires adjudication." if is_conflict else ""
            tier_counts = {
                "T1": sum(1 for tier in tiers if tier == "T1"),
                "T2": sum(1 for tier in tiers if tier == "T2"),
                "T3": sum(1 for tier in tiers if tier == "T3"),
            }
            policy_pass, policy_reason = self._evaluate_claim_source_policy(anchors)
            ledger.append(
                {
                    "claim_text": claim,
                    "anchors": anchors,
                    "source_tier": best_tier,
                    "confidence": round(confidence, 3),
                    "is_core_conclusion": True,
                    "source_policy": self.source_policy,
                    "policy_pass": policy_pass,
                    "policy_reason": policy_reason,
                    "tier_counts": tier_counts,
                    "conflict_status": conflict_status,
                    "resolution_note": resolution_note,
                }
            )
        return ledger

    def _evaluate_claim_source_policy(self, anchors: list[dict[str, Any]]) -> tuple[bool, str]:
        if not anchors:
            return False, "missing_anchor"

        tiers = [str(anchor.get("source_tier") or "T3") for anchor in anchors]
        t1_count = sum(1 for tier in tiers if tier == "T1")
        t2_count = sum(1 for tier in tiers if tier == "T2")

        if self.source_policy == "strict_tier":
            if t1_count < 1:
                return False, "strict_tier_requires_t1_anchor"
            if len(anchors) < 2:
                return False, "strict_tier_requires_multi_anchor"
            return True, "ok"

        if self.source_policy == "medium_tier":
            if (t1_count + t2_count) < 1:
                return False, "medium_tier_requires_t1_or_t2_anchor"
            return True, "ok"

        return True, "ok"

    def _compute_citation_coverage(self) -> dict[str, Any]:
        total_claims = len(self.claim_to_anchors)
        anchored_claims = sum(1 for anchors in self.claim_to_anchors.values() if anchors)
        ratio = anchored_claims / max(1, total_claims)
        by_tier = {"T1": 0, "T2": 0, "T3": 0}
        for anchors in self.claim_to_anchors.values():
            if not anchors:
                continue
            tier = str(anchors[0].get("source_tier") or "T3")
            if tier not in by_tier:
                tier = "T3"
            by_tier[tier] += 1
        core_claims = [item for item in self.claim_ledger if bool(item.get("is_core_conclusion"))]
        core_policy_pass = sum(1 for item in core_claims if bool(item.get("policy_pass")))
        core_policy_fail_examples = [
            {
                "claim_text": item.get("claim_text"),
                "policy_reason": item.get("policy_reason"),
                "source_tier": item.get("source_tier"),
            }
            for item in core_claims
            if not bool(item.get("policy_pass"))
        ][:10]
        return {
            "core_claims_total": total_claims,
            "core_claims_with_anchor": anchored_claims,
            "coverage_ratio": round(ratio, 4),
            "by_tier": by_tier,
            "source_policy": self.source_policy,
            "core_conclusion_policy_total": len(core_claims),
            "core_conclusion_policy_passed": core_policy_pass,
            "core_conclusion_policy_failed": max(0, len(core_claims) - core_policy_pass),
            "core_conclusion_policy_coverage": round(core_policy_pass / max(1, len(core_claims)), 4),
            "core_conclusion_policy_fail_examples": core_policy_fail_examples,
        }

    def _build_final_context(self) -> list[str]:
        facts = self.research_journal["facts"][:80]
        contradictions = self.research_journal["contradictions"][:20]
        pending = self.research_journal["pending"][:20]

        facts_section = ["## Evidence Log"]
        for claim in facts:
            anchors = self.claim_to_anchors.get(claim, [])
            if anchors and anchors[0].get("url"):
                facts_section.append(f"- {claim} ([source]({anchors[0]['url']}))")
            else:
                facts_section.append(f"- {claim}")

        contradiction_section = ["## Conflict Watchlist"]
        if contradictions:
            contradiction_section.extend([f"- {item}" for item in contradictions])
        else:
            contradiction_section.append("- No major source conflicts detected.")

        pending_section = ["## Pending Verification"]
        if pending:
            pending_section.extend([f"- {item}" for item in pending])
        else:
            pending_section.append("- No pending verification items.")

        citation_section = ["## Citation Anchors"]
        for claim, anchors in list(self.claim_to_anchors.items())[:120]:
            for anchor in anchors[:2]:
                url = anchor.get("url", "")
                citation_section.append(
                    f"- {claim} | {url} | {anchor.get('anchor_hash', '')}"
                )

        budget_snapshot = self.budget_manager.export()
        budget_snapshot["global_completed_queries"] = self.completed_queries
        self.trace.set_budget(budget_snapshot)
        return [
            "\n".join(facts_section),
            "\n".join(contradiction_section),
            "\n".join(pending_section),
            "\n".join(citation_section),
        ]

    def _estimate_quality_score(self) -> float:
        """
        Heuristic quality estimate on a 1-10 scale.
        Balances fact count, citation density, and contradiction pressure.
        """
        fact_count = len(self.research_journal["facts"])
        contradiction_count = len(self.research_journal["contradictions"])
        citation_count = sum(len(v) for v in self.claim_to_anchors.values())

        coverage = min(1.0, fact_count / 40.0)
        citation_density = min(1.0, citation_count / max(1.0, fact_count))
        contradiction_penalty = min(1.0, contradiction_count / 10.0)

        score_0_1 = 0.55 * coverage + 0.35 * citation_density - 0.20 * contradiction_penalty
        score_0_1 = max(0.1, min(1.0, score_0_1))
        return round(score_0_1 * 10, 2)
