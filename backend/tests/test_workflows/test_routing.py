"""Tests for H5 Intelligent Routing — auto-recommend next workflow.

Validates:
1. RoutingRule model structure
2. WorkflowRouter.recommend_next() with default rules
3. Each condition evaluator (contradiction, integrity, completion, hypothesis, gene_issues, literature_gaps)
4. Cycle detection and max depth
5. Deduplication by target_template
6. routing_enabled config guard
7. Routing API endpoints
"""

from __future__ import annotations

from app.models.agent import AgentOutput
from app.models.routing import (
    DEFAULT_ROUTING_RULES,
    RoutingRecommendation,
    RoutingRule,
)
from app.models.workflow import WorkflowInstance
from app.workflows.router import WorkflowRouter

# ── Helpers ────────────────────────────────────────────────────────────


def _make_instance(template: str = "W1", state: str = "COMPLETED") -> WorkflowInstance:
    return WorkflowInstance(
        template=template,
        query="test query",
        state=state,
        session_manifest={},
    )


def _make_output(output: dict | None = None, summary: str = "") -> AgentOutput:
    return AgentOutput(agent_id="test", output=output or {}, summary=summary)


# ── H5.1: Routing model structure ─────────────────────────────────────


def test_routing_rule_model():
    rule = RoutingRule(
        source_template="W1",
        condition_type="contradiction_count",
        condition_params={"threshold": 2},
        target_template="W6",
        priority=10,
    )
    assert rule.source_template == "W1"
    assert rule.target_template == "W6"
    assert rule.auto_execute is False


def test_routing_recommendation_model():
    rec = RoutingRecommendation(
        target_template="W6",
        reason="Found contradictions",
        confidence=0.8,
    )
    assert rec.target_template == "W6"
    assert rec.auto_execute is False


def test_default_rules_exist():
    assert len(DEFAULT_ROUTING_RULES) >= 9
    templates = {r.source_template for r in DEFAULT_ROUTING_RULES}
    assert "W1" in templates
    assert "*" in templates  # Wildcard rule


# ── H5.2: WorkflowRouter.recommend_next() ─────────────────────────────


def test_router_empty_for_non_completed():
    router = WorkflowRouter()
    instance = _make_instance(state="RUNNING")
    recs = router.recommend_next(instance, {})
    assert recs == []


def test_router_w1_completion_recommends_w2():
    """Completed W1 with no issues should recommend W2 (standard flow)."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    recs = router.recommend_next(instance, {})
    templates = [r.target_template for r in recs]
    assert "W2" in templates


def test_router_w1_contradictions_recommends_w6():
    """W1 with >2 contradictions should recommend W6."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    step_results = {
        "CONTRADICTION_CHECK": _make_output({
            "contradiction_count": 5,
            "contradictions": [{"id": i} for i in range(5)],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W6" in templates
    # W6 should have higher confidence than W2
    w6_rec = next(r for r in recs if r.target_template == "W6")
    assert w6_rec.confidence > 0.5


def test_router_w1_integrity_error_recommends_w7():
    """W1 with error-level integrity findings should recommend W7."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    step_results = {
        "INTEGRITY_CHECK": _make_output({
            "findings": [
                {"category": "gene_name", "severity": "error", "title": "SEPT1 alias"},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W7" in templates


def test_router_w2_high_hypothesis_recommends_w3():
    """W2 with high-confidence hypothesis should recommend W3."""
    router = WorkflowRouter()
    instance = _make_instance("W2", "COMPLETED")
    step_results = {
        "HYPOTHESIZE": _make_output({
            "hypotheses": [
                {"text": "TP53 regulates apoptosis", "confidence": 0.85},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W3" in templates


# ── H5.3: Condition evaluators ─────────────────────────────────────────


def test_eval_contradiction_below_threshold():
    """Contradictions below threshold should not match."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    step_results = {
        "CONTRADICTION_CHECK": _make_output({
            "contradiction_count": 1,
            "contradictions": [{"id": 1}],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W6" not in templates


def test_eval_integrity_info_level_no_match():
    """Info-level integrity findings should NOT trigger W7."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    step_results = {
        "INTEGRITY_CHECK": _make_output({
            "findings": [
                {"category": "other", "severity": "info", "title": "minor note"},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    # W7 should NOT be recommended for info-level
    w7_recs = [r for r in recs if r.target_template == "W7"]
    assert not w7_recs or all(r.confidence < 0.5 for r in w7_recs)


def test_eval_gene_issues_wildcard():
    """Wildcard rule (*) should match gene issues from any template."""
    router = WorkflowRouter()
    instance = _make_instance("W3", "COMPLETED")
    step_results = {
        "INTEGRITY_CHECK": _make_output({
            "findings": [
                {"category": "gene_name", "severity": "warning", "title": "DEC1→BHLHE40"},
                {"category": "gene_name", "severity": "warning", "title": "SEPT1→SEPTIN1"},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W7" in templates


def test_eval_literature_gaps():
    """W8 with literature gaps should recommend W1."""
    router = WorkflowRouter()
    instance = _make_instance("W8", "COMPLETED")
    step_results = {
        "SYNTHESIZE_REVIEW": _make_output({
            "literature_gaps": ["Missing recent studies on TP53 splicing"],
            "major_comments": [
                "The authors should discuss relevant literature on TP53 variants",
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W1" in templates


# ── H5.4: Cycle detection ─────────────────────────────────────────────


def test_cycle_detection_max_depth():
    """Router should stop at max routing depth."""
    router = WorkflowRouter(max_depth=3)
    instance = _make_instance("W1", "COMPLETED")
    instance.session_manifest = {"routing_chain": ["W8", "W1", "W6"]}
    recs = router.recommend_next(instance, {})
    assert recs == []


def test_cycle_detection_skip_visited():
    """Router should skip templates already in the routing chain."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    instance.session_manifest = {"routing_chain": ["W2"]}
    recs = router.recommend_next(instance, {})
    templates = [r.target_template for r in recs]
    # W2 should be skipped because it's already in the chain
    assert "W2" not in templates


# ── H5.5: Deduplication ───────────────────────────────────────────────


def test_deduplication_by_template():
    """Multiple rules matching same target should be deduplicated."""
    rules = [
        RoutingRule(
            source_template="W1", condition_type="completion",
            target_template="W7", priority=1,
        ),
        RoutingRule(
            source_template="*", condition_type="gene_issues",
            condition_params={"threshold": 1},
            target_template="W7", priority=8,
        ),
    ]
    router = WorkflowRouter(rules=rules)
    instance = _make_instance("W1", "COMPLETED")
    step_results = {
        "INTEGRITY_CHECK": _make_output({
            "findings": [
                {"category": "gene_name", "severity": "warning", "title": "issue1"},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    w7_count = sum(1 for r in recs if r.target_template == "W7")
    assert w7_count == 1


# ── H5.6: Config guard ────────────────────────────────────────────────


def test_routing_disabled_by_default():
    from app.config import settings
    assert settings.routing_enabled is False


# ── H5.7: Hypothesis score below threshold ────────────────────────────


def test_low_hypothesis_no_w3():
    """W2 with low hypothesis score should NOT recommend W3."""
    router = WorkflowRouter()
    instance = _make_instance("W2", "COMPLETED")
    step_results = {
        "HYPOTHESIZE": _make_output({
            "hypotheses": [
                {"text": "Weak hypothesis", "confidence": 0.3},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    # W3 might appear from completion rule, but hypothesis rule shouldn't match
    hyp_recs = [r for r in recs if r.rule_id and "hypothesis_score" in r.rule_id]
    assert len(hyp_recs) == 0


# ── H5.8: Recommendation sorting by confidence ────────────────────────


def test_recommendations_sorted_by_confidence():
    """Recommendations should be sorted highest confidence first."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    step_results = {
        "CONTRADICTION_CHECK": _make_output({
            "contradiction_count": 5,
            "contradictions": [{"id": i} for i in range(5)],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    if len(recs) >= 2:
        for i in range(len(recs) - 1):
            assert recs[i].confidence >= recs[i + 1].confidence


# ── H5.9: W9 gene issues → W7 ────────────────────────────────────────


def test_w9_gene_issues_recommends_w7():
    """W9 with gene name issues should recommend W7."""
    router = WorkflowRouter()
    instance = _make_instance("W9", "COMPLETED")
    step_results = {
        "GENOMIC_ANALYSIS": _make_output({
            "findings": [
                {"category": "gene_name", "severity": "warning", "title": "MARCH1→MARCHF1"},
            ],
        }),
    }
    recs = router.recommend_next(instance, step_results)
    templates = [r.target_template for r in recs]
    assert "W7" in templates


# ── H5.10: Empty step results ─────────────────────────────────────────


def test_empty_step_results_only_completion():
    """With empty step results, only completion rules should match."""
    router = WorkflowRouter()
    instance = _make_instance("W1", "COMPLETED")
    recs = router.recommend_next(instance, {})
    # Only completion-based rules should fire
    for rec in recs:
        if rec.rule_id:
            assert "completion" in rec.rule_id
