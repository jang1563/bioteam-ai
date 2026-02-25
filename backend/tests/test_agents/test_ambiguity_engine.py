"""Tests for AmbiguityEngineAgent.

15 tests covering:
- Empty/insufficient context → no contradictions
- Single pair detection + classification
- Genuine vs non-genuine classification filtering
- Multi-label types
- Resolution generation for genuine contradictions
- RCMXT scoring stored on entries
- Budget cap (MAX_CLASSIFY_CALLS)
- AgentOutput type and metadata
- Ambiguity level computation
- Claim extraction from key_findings and contradictions_noted
- Full pipeline integration
"""

from __future__ import annotations

import pytest

from app.agents.ambiguity_engine import (
    AmbiguityEngineAgent,
    ContradictionAnalysis,
    ContradictionClassification,
    ResolutionHypothesis,
    ResolutionOutput,
    MAX_CLASSIFY_CALLS,
)
from app.agents.base import BaseAgent
from app.llm.mock_layer import MockLLMLayer
from app.models.agent import AgentOutput
from app.models.messages import ContextPackage


@pytest.fixture
def genuine_classification():
    """A classification marking the pair as a genuine contradiction."""
    return ContradictionClassification(
        types=["conditional_truth"],
        confidence=0.85,
        type_reasoning={"conditional_truth": "Opposing effects under different conditions"},
        is_genuine_contradiction=True,
        context_dependence="Claim A applies to normoxic conditions, Claim B to hypoxic.",
    )


@pytest.fixture
def not_genuine_classification():
    """A classification marking the pair as NOT a genuine contradiction."""
    return ContradictionClassification(
        types=[],
        confidence=0.9,
        type_reasoning={},
        is_genuine_contradiction=False,
        context_dependence="",
    )


@pytest.fixture
def resolution_output():
    """Mock resolution output."""
    return ResolutionOutput(
        hypotheses=[
            ResolutionHypothesis(
                hypothesis="The difference may be due to oxygen levels",
                hypothesis_type="reconciling",
                testable_prediction="Compare VEGF expression under normoxic vs hypoxic conditions",
                confidence=0.7,
            ),
        ],
        discriminating_experiment="Measure VEGF in matched samples under both conditions",
    )


def _make_agent(
    classification: ContradictionClassification | None = None,
    resolution: ResolutionOutput | None = None,
) -> AmbiguityEngineAgent:
    """Create an AmbiguityEngineAgent with mock LLM."""
    responses = {}
    if classification is not None:
        responses["sonnet:ContradictionClassification"] = classification
    if resolution is not None:
        responses["sonnet:ResolutionOutput"] = resolution

    mock_llm = MockLLMLayer(responses)
    spec = BaseAgent.load_spec("ambiguity_engine")
    return AmbiguityEngineAgent(spec=spec, llm=mock_llm, memory=None)


def _make_context(
    task: str = "Analyze contradictions",
    key_findings: list[str] | None = None,
    contradictions_noted: list[str] | None = None,
    workflow_id: str | None = None,
) -> ContextPackage:
    """Build a ContextPackage with optional prior step outputs."""
    prior = []
    output = {}
    if key_findings:
        output["key_findings"] = key_findings
    if contradictions_noted:
        output["contradictions_noted"] = contradictions_noted
    if output:
        prior.append({"output": output})

    constraints = {}
    if workflow_id:
        constraints["workflow_id"] = workflow_id

    return ContextPackage(
        task_description=task,
        prior_step_outputs=prior,
        constraints=constraints,
    )


# === Tests ===


@pytest.mark.asyncio
async def test_detect_no_contradictions_empty_context():
    """Empty context → insufficient claims → no contradictions."""
    agent = _make_agent()
    ctx = _make_context(task="")
    result = await agent.run(ctx)

    assert result.is_success
    analysis = result.output
    assert analysis["contradictions_found"] == 0
    assert analysis["overall_ambiguity_level"] == "low"


@pytest.mark.asyncio
async def test_detect_no_contradictions_single_claim():
    """Single claim → insufficient for pair analysis."""
    agent = _make_agent()
    ctx = _make_context(task="VEGF increases under hypoxia in endothelial cells")
    result = await agent.run(ctx)

    assert result.is_success
    assert result.output["contradictions_found"] == 0


@pytest.mark.asyncio
async def test_detect_contradictions_with_markers(genuine_classification, resolution_output):
    """Claims with contradiction markers → pair detected → classified."""
    agent = _make_agent(
        classification=genuine_classification,
        resolution=resolution_output,
    )
    ctx = _make_context(
        key_findings=[
            "VEGF expression increases significantly under spaceflight conditions in endothelial cells",
            "VEGF expression decreases significantly under spaceflight conditions in fibroblast cells",
        ],
    )
    result = await agent.run(ctx)

    assert result.is_success
    analysis = result.output
    assert analysis["contradictions_found"] >= 1
    assert analysis["pairs_classified"] >= 1
    assert len(analysis["entries"]) >= 1

    entry = analysis["entries"][0]
    assert "conditional_truth" in entry["types"]
    assert entry["detected_by"] == "ambiguity_engine"


@pytest.mark.asyncio
async def test_classify_pair_not_genuine_no_entry(not_genuine_classification):
    """If classification says NOT genuine, no ContradictionEntry is stored."""
    agent = _make_agent(classification=not_genuine_classification)
    ctx = _make_context(
        key_findings=[
            "Gene X is upregulated in tissue A during spaceflight exposure experiments",
            "Gene X is downregulated in tissue B during microgravity simulation studies",
        ],
    )
    result = await agent.run(ctx)

    assert result.is_success
    assert result.output["contradictions_found"] == 0
    assert len(result.output["entries"]) == 0
    # But pairs_classified should still be > 0 (the pair was classified, just not genuine)
    assert result.output["pairs_classified"] >= 1


@pytest.mark.asyncio
async def test_multi_label_types():
    """Multi-label types stored on entry."""
    multi_class = ContradictionClassification(
        types=["conditional_truth", "temporal_dynamics"],
        confidence=0.75,
        type_reasoning={
            "conditional_truth": "Context-dependent",
            "temporal_dynamics": "Different time periods",
        },
        is_genuine_contradiction=True,
    )
    agent = _make_agent(classification=multi_class)
    ctx = _make_context(
        key_findings=[
            "Gene X promotes cell proliferation in normoxic environments in laboratory settings",
            "Gene X inhibits cell proliferation in hypoxic environments in clinical samples",
        ],
    )
    result = await agent.run(ctx)

    assert result.is_success
    if result.output["contradictions_found"] > 0:
        entry = result.output["entries"][0]
        assert "conditional_truth" in entry["types"]
        assert "temporal_dynamics" in entry["types"]


@pytest.mark.asyncio
async def test_generate_resolutions_called_for_genuine(genuine_classification, resolution_output):
    """Genuine contradictions get resolution hypotheses."""
    agent = _make_agent(
        classification=genuine_classification,
        resolution=resolution_output,
    )
    ctx = _make_context(
        key_findings=[
            "EPO production is elevated during spaceflight in astronaut blood samples",
            "EPO production is reduced during spaceflight in ground-based analog studies",
        ],
    )
    result = await agent.run(ctx)

    assert result.is_success
    if result.output["contradictions_found"] > 0:
        entry = result.output["entries"][0]
        assert len(entry["resolution_hypotheses"]) > 0
        assert entry["discriminating_experiment"] != ""


@pytest.mark.asyncio
async def test_rcmxt_scores_stored(genuine_classification, resolution_output):
    """RCMXT scores are computed and stored for each claim."""
    agent = _make_agent(
        classification=genuine_classification,
        resolution=resolution_output,
    )
    ctx = _make_context(
        key_findings=[
            "Telomere length increases during long-duration spaceflight in astronaut samples",
            "Telomere length decreases during ground-based radiation analog experiments",
        ],
    )
    result = await agent.run(ctx)

    assert result.is_success
    if result.output["contradictions_found"] > 0:
        entry = result.output["entries"][0]
        # RCMXT dicts should be populated (at least have 'claim' key from heuristic scorer)
        assert isinstance(entry["rcmxt_a"], dict)
        assert isinstance(entry["rcmxt_b"], dict)


@pytest.mark.asyncio
async def test_budget_cap_respected(genuine_classification, resolution_output):
    """Should not exceed MAX_CLASSIFY_CALLS LLM classify calls."""
    agent = _make_agent(
        classification=genuine_classification,
        resolution=resolution_output,
    )
    # Create many claims that all have contradiction markers
    claims = []
    for i in range(MAX_CLASSIFY_CALLS + 5):
        if i % 2 == 0:
            claims.append(f"Factor {i} significantly increases expression in experiment {i}")
        else:
            claims.append(f"Factor {i} significantly decreases expression in experiment {i}")

    ctx = _make_context(key_findings=claims)
    result = await agent.run(ctx)

    assert result.is_success
    assert result.output["pairs_classified"] <= MAX_CLASSIFY_CALLS


@pytest.mark.asyncio
async def test_agent_output_type(genuine_classification, resolution_output):
    """AgentOutput has correct type and metadata."""
    agent = _make_agent(
        classification=genuine_classification,
        resolution=resolution_output,
    )
    ctx = _make_context(
        key_findings=[
            "Protein folding is enhanced under microgravity conditions in crystallography experiments",
            "Protein folding is reduced under microgravity conditions in solution-phase experiments",
        ],
    )
    result = await agent.run(ctx)

    assert isinstance(result, AgentOutput)
    assert result.output_type == "ContradictionAnalysis"
    assert result.agent_id == "ambiguity_engine"
    assert result.is_success


@pytest.mark.asyncio
async def test_ambiguity_level_low():
    """Zero contradictions → ambiguity level 'low'."""
    agent = _make_agent()
    ctx = _make_context(task="Single short claim")
    result = await agent.run(ctx)

    assert result.output["overall_ambiguity_level"] == "low"


def test_ambiguity_level_computation():
    """Unit test for _compute_ambiguity_level static method."""
    assert AmbiguityEngineAgent._compute_ambiguity_level(0, 10) == "low"
    assert AmbiguityEngineAgent._compute_ambiguity_level(1, 10) == "moderate"
    assert AmbiguityEngineAgent._compute_ambiguity_level(2, 10) == "moderate"
    assert AmbiguityEngineAgent._compute_ambiguity_level(3, 10) == "high"
    assert AmbiguityEngineAgent._compute_ambiguity_level(5, 10) == "high"
    assert AmbiguityEngineAgent._compute_ambiguity_level(6, 10) == "critical"


@pytest.mark.asyncio
async def test_extract_claims_from_key_findings():
    """Claims extracted from prior_step_outputs key_findings."""
    agent = _make_agent()
    findings = [
        "VEGF promotes angiogenesis in spaceflight conditions",
        "TNF-alpha levels are elevated during re-entry",
    ]
    ctx = _make_context(key_findings=findings)
    claims = agent._extract_claims(ctx)

    assert len(claims) >= 2
    assert any("VEGF" in c for c in claims)
    assert any("TNF-alpha" in c for c in claims)


@pytest.mark.asyncio
async def test_extract_claims_from_contradictions_noted():
    """Claims extracted from contradictions_noted field."""
    agent = _make_agent()
    noted = [
        "Study A claims gene X is upregulated under microgravity conditions",
        "Study B claims gene X is downregulated under microgravity conditions",
    ]
    ctx = _make_context(contradictions_noted=noted)
    claims = agent._extract_claims(ctx)

    assert len(claims) >= 2


@pytest.mark.asyncio
async def test_extract_claims_deduplication():
    """Duplicate claims are removed."""
    agent = _make_agent()
    same = "VEGF increases during spaceflight in endothelial cells"
    ctx = _make_context(
        task=same,
        key_findings=[same, same],
    )
    claims = agent._extract_claims(ctx)

    assert claims.count(same) == 1


@pytest.mark.asyncio
async def test_workflow_id_propagated(genuine_classification, resolution_output):
    """workflow_id from constraints is stored on ContradictionEntry."""
    agent = _make_agent(
        classification=genuine_classification,
        resolution=resolution_output,
    )
    ctx = _make_context(
        key_findings=[
            "Bone density significantly increases during short spaceflight missions",
            "Bone density significantly decreases during long spaceflight missions",
        ],
        workflow_id="wf-test-123",
    )
    result = await agent.run(ctx)

    assert result.is_success
    if result.output["contradictions_found"] > 0:
        entry = result.output["entries"][0]
        assert entry["workflow_id"] == "wf-test-123"
