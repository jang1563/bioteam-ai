"""Comprehensive API input fuzzing tests for BioTeam-AI backend.

Tests edge cases, boundary values, injection attempts, and malformed
payloads across all major API endpoints:
  - POST /api/v1/workflows (CreateWorkflowRequest)
  - POST /api/v1/workflows/{id}/intervene (InterveneRequest)
  - POST /api/v1/negative-results (CreateNegativeResultRequest)
  - PUT  /api/v1/negative-results/{id} (UpdateNegativeResultRequest)

Uses separate FastAPI apps without middleware so validation is tested
in isolation (no rate-limit or auth interference).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.negative_results import router as nr_router
from app.api.v1.workflows import router as wf_router, set_dependencies
from app.db.database import engine as db_engine, create_db_and_tables
from app.agents.registry import create_registry
from app.llm.mock_layer import MockLLMLayer
from app.workflows.engine import WorkflowEngine


# ---------------------------------------------------------------------------
# Test client factories
# ---------------------------------------------------------------------------

def _nr_client() -> TestClient:
    """Create a test client for negative-results endpoints (no middleware)."""
    create_db_and_tables()
    test_app = FastAPI()
    test_app.include_router(nr_router)
    return TestClient(test_app)


def _wf_client() -> TestClient:
    """Create a test client for workflow endpoints (no middleware)."""
    create_db_and_tables()
    test_app = FastAPI()
    test_app.include_router(wf_router)
    mock = MockLLMLayer()
    registry = create_registry(mock)
    engine = WorkflowEngine()
    set_dependencies(registry, engine)
    return TestClient(test_app)


def _create_nr(client: TestClient, **overrides) -> dict:
    """Helper: create a valid negative-result entry and return the JSON."""
    payload = {
        "claim": "Drug X inhibits target Y",
        "outcome": "No inhibition observed at 10uM",
        "source": "internal",
        "confidence": 0.7,
        "failure_category": "protocol",
        **overrides,
    }
    resp = client.post("/api/v1/negative-results", json=payload)
    assert resp.status_code == 201, f"Setup failed: {resp.text}"
    return resp.json()


def _create_wf(client: TestClient, **overrides) -> dict:
    """Helper: create a valid workflow and return the JSON."""
    payload = {"template": "W1", "query": "test query", **overrides}
    resp = client.post("/api/v1/workflows", json=payload)
    assert resp.status_code == 200, f"Setup failed: {resp.text}"
    return resp.json()


# ===================================================================
#  Common payloads used across multiple tests
# ===================================================================

SQL_INJECTION_STRINGS = [
    "'; DROP TABLE workflow_instance; --",
    "1; SELECT * FROM negative_result --",
    "' OR '1'='1",
    "Robert'); DROP TABLE negative_result;--",
    "1 UNION SELECT * FROM negative_result",
    "admin'--",
]

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    '<img src=x onerror="alert(1)">',
    "javascript:alert(document.cookie)",
    '"><svg onload=alert(1)>',
    "<iframe src='javascript:alert(1)'></iframe>",
    "{{7*7}}",  # Template injection
]

UNICODE_STRINGS = [
    "Homo sapiens\u00a0p53\u2013dependent apoptosis",  # non-breaking space, en-dash
    "\u00e9\u00e8\u00ea\u00eb\u00e0\u00e2\u00e4\u00fc\u00f6\u00df",  # French/German accents
    "\u4e2d\u6587\u7814\u7a76\u62a5\u544a",  # Chinese characters
    "\U0001f9ec\U0001f9a0\U0001f52c",  # emoji: DNA, microbe, microscope (full codepoints)
    "\u202eRTL override",  # right-to-left override char
    "\t\n\r\f\v",  # whitespace control chars
    "a" * 0 + "\u200b",  # zero-width space only
]


# ===================================================================
#  1. POST /api/v1/workflows — CreateWorkflowRequest fuzzing
# ===================================================================

class TestWorkflowCreateFuzzing:
    """Fuzzing tests for POST /api/v1/workflows."""

    # --- template field ---

    def test_template_empty_string(self):
        """Empty template should be rejected (pattern ^W[1-6]$)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "", "query": "test"})
        assert resp.status_code == 422

    def test_template_lowercase(self):
        """Lowercase 'w1' should be rejected (pattern is uppercase W)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "w1", "query": "test"})
        assert resp.status_code == 422

    def test_template_w0_out_of_range(self):
        """W0 should be rejected (only W1-W6)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "W0", "query": "test"})
        assert resp.status_code == 422

    def test_template_w7_out_of_range(self):
        """W7 should be rejected (only W1-W6)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "W7", "query": "test"})
        assert resp.status_code == 422

    def test_template_w1_with_trailing_space(self):
        """'W1 ' with trailing space should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "W1 ", "query": "test"})
        assert resp.status_code == 422

    def test_template_w1_with_leading_space(self):
        """' W1' with leading space should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": " W1", "query": "test"})
        assert resp.status_code == 422

    def test_template_sql_injection(self):
        """SQL injection in template field should be rejected."""
        client = _wf_client()
        for payload in SQL_INJECTION_STRINGS:
            resp = client.post("/api/v1/workflows", json={"template": payload, "query": "test"})
            assert resp.status_code == 422, f"SQL injection not rejected: {payload}"

    def test_template_xss(self):
        """XSS in template field should be rejected."""
        client = _wf_client()
        for payload in XSS_PAYLOADS:
            resp = client.post("/api/v1/workflows", json={"template": payload, "query": "test"})
            assert resp.status_code == 422, f"XSS not rejected: {payload}"

    def test_template_null(self):
        """null template should be rejected (required field)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": None, "query": "test"})
        assert resp.status_code == 422

    def test_template_integer(self):
        """Integer 1 for template should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": 1, "query": "test"})
        assert resp.status_code == 422

    def test_template_missing(self):
        """Missing template field should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"query": "test"})
        assert resp.status_code == 422

    # --- query field ---

    def test_query_empty_string(self):
        """Empty query should be rejected (min_length=1)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "W1", "query": ""})
        assert resp.status_code == 422

    def test_query_max_length_boundary(self):
        """Exactly 2000 chars should be accepted."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "x" * 2000,
        })
        assert resp.status_code == 200

    def test_query_exceeds_max_length(self):
        """2001 chars should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "x" * 2001,
        })
        assert resp.status_code == 422

    def test_query_sql_injection_accepted_as_text(self):
        """SQL injection in query is valid text (min 1, max 2000) -- should be accepted."""
        client = _wf_client()
        for payload in SQL_INJECTION_STRINGS:
            resp = client.post("/api/v1/workflows", json={
                "template": "W1",
                "query": payload,
            })
            # query has no pattern constraint, so SQL strings are valid text
            assert resp.status_code == 200, f"Valid text rejected: {payload}"

    def test_query_xss_accepted_as_text(self):
        """XSS in query is valid text -- should be accepted (output encoding is separate)."""
        client = _wf_client()
        for payload in XSS_PAYLOADS:
            resp = client.post("/api/v1/workflows", json={
                "template": "W1",
                "query": payload,
            })
            assert resp.status_code == 200, f"Valid text rejected: {payload}"

    def test_query_unicode_accepted(self):
        """Unicode strings in query field should be accepted."""
        client = _wf_client()
        for text in UNICODE_STRINGS:
            # Skip strings that are effectively empty or contain control chars
            if not text.strip():
                continue
            resp = client.post("/api/v1/workflows", json={
                "template": "W1",
                "query": text,
            })
            assert resp.status_code == 200, f"Unicode rejected: {repr(text)}"

    def test_query_emoji_accepted(self):
        """Emoji-heavy query should be accepted."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "\U0001f9ec DNA repair in \U0001f42d mouse models \U0001f52c",
        })
        assert resp.status_code == 200

    def test_query_missing(self):
        """Missing query field should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={"template": "W1"})
        assert resp.status_code == 422

    # --- budget field ---

    def test_budget_lower_boundary_exact(self):
        """budget=0.1 (minimum) should be accepted."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": 0.1,
        })
        assert resp.status_code == 200

    def test_budget_upper_boundary_exact(self):
        """budget=100.0 (maximum) should be accepted."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": 100.0,
        })
        assert resp.status_code == 200

    def test_budget_below_minimum(self):
        """budget=0.09 should be rejected (ge=0.1)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": 0.09,
        })
        assert resp.status_code == 422

    def test_budget_above_maximum(self):
        """budget=100.01 should be rejected (le=100.0)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": 100.01,
        })
        assert resp.status_code == 422

    def test_budget_zero(self):
        """budget=0.0 should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": 0.0,
        })
        assert resp.status_code == 422

    def test_budget_negative(self):
        """Negative budget should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": -5.0,
        })
        assert resp.status_code == 422

    def test_budget_string_type(self):
        """String budget should be coerced or rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": "not_a_number",
        })
        assert resp.status_code == 422

    def test_budget_very_large_number(self):
        """Extremely large budget should be rejected (le=100.0)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": 1e18,
        })
        assert resp.status_code == 422

    def test_budget_default_when_omitted(self):
        """Omitting budget should use default (5.0)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test",
        })
        assert resp.status_code == 200
        # Verify the workflow was created with default budget
        wf_id = resp.json()["workflow_id"]
        resp2 = client.get(f"/api/v1/workflows/{wf_id}")
        assert resp2.status_code == 200
        assert resp2.json()["budget_total"] == 5.0

    # --- seed_papers field ---

    def test_seed_papers_empty_list(self):
        """Empty seed_papers list should be accepted (default)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "seed_papers": [],
        })
        assert resp.status_code == 200

    def test_seed_papers_valid_dois(self):
        """Valid DOI list should be accepted."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "seed_papers": ["10.1038/s41586-023-06380-y", "10.1126/science.abm5759"],
        })
        assert resp.status_code == 200

    def test_seed_papers_exceeds_max_50(self):
        """More than 50 seed papers should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "seed_papers": [f"10.1000/paper-{i}" for i in range(51)],
        })
        assert resp.status_code == 422

    def test_seed_papers_exactly_50(self):
        """Exactly 50 seed papers should be accepted."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "seed_papers": [f"10.1000/paper-{i}" for i in range(50)],
        })
        assert resp.status_code == 200

    def test_seed_papers_sql_injection_in_items(self):
        """SQL injection in seed paper strings should be accepted (valid text)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "seed_papers": SQL_INJECTION_STRINGS[:3],
        })
        assert resp.status_code == 200

    # --- extra unknown fields ---

    def test_extra_fields_ignored(self):
        """Unknown fields should be silently ignored."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "unknown_field": "should_be_ignored",
            "another_unknown": 42,
        })
        assert resp.status_code == 200

    # --- completely invalid payloads ---

    def test_empty_json_body(self):
        """Empty JSON body should be rejected (missing required fields)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={})
        assert resp.status_code == 422

    def test_non_json_body(self):
        """Non-JSON body should be rejected."""
        client = _wf_client()
        resp = client.post(
            "/api/v1/workflows",
            content="this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_array_instead_of_object(self):
        """JSON array instead of object should be rejected."""
        client = _wf_client()
        resp = client.post(
            "/api/v1/workflows",
            content='[{"template":"W1","query":"test"}]',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


# ===================================================================
#  2. POST /api/v1/workflows/{id}/intervene — InterveneRequest fuzzing
# ===================================================================

class TestWorkflowInterveneFuzzing:
    """Fuzzing tests for POST /api/v1/workflows/{id}/intervene."""

    def test_action_invalid_string(self):
        """Invalid action literal should be rejected."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "destroy",
        })
        assert resp.status_code == 422

    def test_action_empty_string(self):
        """Empty action should be rejected."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "",
        })
        assert resp.status_code == 422

    def test_action_sql_injection(self):
        """SQL injection in action field should be rejected (Literal type)."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "'; DROP TABLE workflow_instance;--",
        })
        assert resp.status_code == 422

    def test_action_missing(self):
        """Missing action field should be rejected."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "note": "test",
        })
        assert resp.status_code == 422

    def test_note_exceeds_max_length(self):
        """Note longer than 2000 chars should be rejected."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "inject_note",
            "note": "x" * 2001,
        })
        assert resp.status_code == 422

    def test_note_at_max_length(self):
        """Note at exactly 2000 chars should be accepted."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "inject_note",
            "note": "x" * 2000,
        })
        assert resp.status_code == 200

    def test_note_action_invalid_pattern(self):
        """Invalid note_action pattern should be rejected."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "inject_note",
            "note": "test",
            "note_action": "INVALID_ACTION",
        })
        assert resp.status_code == 422

    def test_note_action_sql_injection(self):
        """SQL injection in note_action should be rejected (pattern constraint)."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "inject_note",
            "note": "test",
            "note_action": "'; DROP TABLE workflow_instance;--",
        })
        assert resp.status_code == 422

    def test_inject_note_without_note_text(self):
        """inject_note action without note text should return 400."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "inject_note",
        })
        # The endpoint checks for empty note and raises 400
        assert resp.status_code == 400

    def test_intervene_nonexistent_workflow(self):
        """Intervening on a nonexistent workflow should return 404."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows/nonexistent-id/intervene", json={
            "action": "cancel",
        })
        assert resp.status_code == 404

    def test_note_with_xss_payload(self):
        """XSS in note text should be accepted (it is free-form text)."""
        client = _wf_client()
        wf = _create_wf(client)
        for payload in XSS_PAYLOADS:
            resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
                "action": "inject_note",
                "note": payload,
            })
            # Note text is free-form -- XSS is valid text; output encoding handles safety
            assert resp.status_code == 200, f"Valid note text rejected: {payload}"

    def test_note_with_unicode(self):
        """Unicode in note text should be accepted."""
        client = _wf_client()
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "inject_note",
            "note": "\U0001f9ec Focus on p53\u2013dependent pathways in \u4e2d\u6587",
        })
        assert resp.status_code == 200


# ===================================================================
#  3. POST /api/v1/negative-results — CreateNegativeResultRequest fuzzing
# ===================================================================

class TestNegativeResultCreateFuzzing:
    """Fuzzing tests for POST /api/v1/negative-results."""

    # --- claim field ---

    def test_claim_empty_string(self):
        """Empty claim should be rejected (min_length=1)."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "",
            "outcome": "result",
            "source": "internal",
        })
        assert resp.status_code == 422

    def test_claim_exceeds_max_length(self):
        """Claim over 2000 chars should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "a" * 2001,
            "outcome": "result",
            "source": "internal",
        })
        assert resp.status_code == 422

    def test_claim_at_max_length(self):
        """Claim at exactly 2000 chars should be accepted."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "a" * 2000,
            "outcome": "result",
            "source": "internal",
        })
        assert resp.status_code == 201

    def test_claim_sql_injection(self):
        """SQL injection in claim should be accepted (free-form text)."""
        client = _nr_client()
        for payload in SQL_INJECTION_STRINGS:
            resp = client.post("/api/v1/negative-results", json={
                "claim": payload,
                "outcome": "result",
                "source": "internal",
            })
            assert resp.status_code == 201, f"Valid claim rejected: {payload}"

    def test_claim_xss(self):
        """XSS in claim should be accepted (free-form text)."""
        client = _nr_client()
        for payload in XSS_PAYLOADS:
            resp = client.post("/api/v1/negative-results", json={
                "claim": payload,
                "outcome": "result",
                "source": "internal",
            })
            assert resp.status_code == 201, f"Valid claim rejected: {payload}"

    def test_claim_unicode(self):
        """Unicode strings in claim should be accepted."""
        client = _nr_client()
        for text in UNICODE_STRINGS:
            if not text.strip():
                continue
            resp = client.post("/api/v1/negative-results", json={
                "claim": text,
                "outcome": "result",
                "source": "internal",
            })
            assert resp.status_code == 201, f"Unicode claim rejected: {repr(text)}"

    def test_claim_missing(self):
        """Missing claim should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "outcome": "result",
            "source": "internal",
        })
        assert resp.status_code == 422

    # --- outcome field ---

    def test_outcome_empty_string(self):
        """Empty outcome should be rejected (min_length=1)."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test",
            "outcome": "",
            "source": "internal",
        })
        assert resp.status_code == 422

    def test_outcome_exceeds_max_length(self):
        """Outcome over 2000 chars should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test",
            "outcome": "b" * 2001,
            "source": "internal",
        })
        assert resp.status_code == 422

    # --- source field ---

    def test_source_invalid_enum(self):
        """Invalid source should be rejected (pattern constraint)."""
        client = _nr_client()
        for invalid_src in ["INVALID", "external", "lab", "Internal", "INTERNAL", ""]:
            resp = client.post("/api/v1/negative-results", json={
                "claim": "test",
                "outcome": "result",
                "source": invalid_src,
            })
            assert resp.status_code == 422, f"Invalid source accepted: {invalid_src}"

    def test_source_all_valid_values(self):
        """All four valid source values should be accepted."""
        client = _nr_client()
        for valid_src in ["internal", "clinical_trial", "shadow", "preprint_delta"]:
            resp = client.post("/api/v1/negative-results", json={
                "claim": "test claim",
                "outcome": "test result",
                "source": valid_src,
            })
            assert resp.status_code == 201, f"Valid source rejected: {valid_src}"

    def test_source_sql_injection(self):
        """SQL injection in source should be rejected (pattern constraint)."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test",
            "outcome": "result",
            "source": "'; DROP TABLE negative_result;--",
        })
        assert resp.status_code == 422

    def test_source_missing(self):
        """Missing source should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test",
            "outcome": "result",
        })
        assert resp.status_code == 422

    # --- confidence field ---

    def test_confidence_lower_boundary(self):
        """confidence=0.0 should be accepted (ge=0.0)."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": 0.0,
        })
        assert resp.status_code == 201

    def test_confidence_upper_boundary(self):
        """confidence=1.0 should be accepted (le=1.0)."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": 1.0,
        })
        assert resp.status_code == 201

    def test_confidence_below_minimum(self):
        """confidence=-0.1 should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": -0.1,
        })
        assert resp.status_code == 422

    def test_confidence_above_maximum(self):
        """confidence=1.1 should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": 1.1,
        })
        assert resp.status_code == 422

    def test_confidence_string_type(self):
        """String confidence should be coerced or rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": "high",
        })
        assert resp.status_code == 422

    def test_confidence_negative_large(self):
        """Very negative confidence should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": -999.0,
        })
        assert resp.status_code == 422

    def test_confidence_very_large(self):
        """Very large confidence should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "confidence": 999.0,
        })
        assert resp.status_code == 422

    def test_confidence_default_when_omitted(self):
        """Omitting confidence should use default (0.5)."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
        })
        assert resp.status_code == 201
        assert resp.json()["confidence"] == 0.5

    # --- failure_category field ---

    def test_failure_category_invalid(self):
        """Invalid failure_category should be rejected (pattern constraint)."""
        client = _nr_client()
        for invalid_cat in ["invalid", "other", "Protocol", "PROTOCOL"]:
            resp = client.post("/api/v1/negative-results", json={
                "claim": "test", "outcome": "result", "source": "internal",
                "failure_category": invalid_cat,
            })
            assert resp.status_code == 422, f"Invalid category accepted: {invalid_cat}"

    def test_failure_category_all_valid(self):
        """All valid failure categories should be accepted, including empty string."""
        client = _nr_client()
        for valid_cat in ["protocol", "reagent", "analysis", "biological", ""]:
            resp = client.post("/api/v1/negative-results", json={
                "claim": "test", "outcome": "result", "source": "internal",
                "failure_category": valid_cat,
            })
            assert resp.status_code == 201, f"Valid category rejected: {repr(valid_cat)}"

    # --- conditions field (dict) ---

    def test_conditions_deeply_nested(self):
        """Deeply nested dict should be accepted."""
        client = _nr_client()
        nested = {"level1": {"level2": {"level3": {"level4": {"level5": "deep"}}}}}
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "conditions": nested,
        })
        assert resp.status_code == 201
        assert resp.json()["conditions"]["level1"]["level2"]["level3"]["level4"]["level5"] == "deep"

    def test_conditions_with_sql_injection_values(self):
        """SQL injection in conditions values should be stored safely."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "conditions": {"key": "'; DROP TABLE negative_result;--"},
        })
        assert resp.status_code == 201
        assert "DROP TABLE" in resp.json()["conditions"]["key"]

    def test_conditions_large_dict(self):
        """Large dict with many keys should be accepted."""
        client = _nr_client()
        big_conditions = {f"key_{i}": f"value_{i}" for i in range(100)}
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "conditions": big_conditions,
        })
        assert resp.status_code == 201

    def test_conditions_with_mixed_types(self):
        """Dict with mixed value types should be accepted."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "conditions": {
                "temperature": 37.5,
                "cell_line": "HeLa",
                "replicas": 3,
                "is_blinded": True,
                "notes": None,
                "reagents": ["compound_A", "compound_B"],
            },
        })
        assert resp.status_code == 201

    # --- implications field (list) ---

    def test_implications_with_xss(self):
        """XSS in implications list items should be stored as text."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "implications": XSS_PAYLOADS[:3],
        })
        assert resp.status_code == 201
        stored = resp.json()["implications"]
        assert len(stored) == 3

    # --- extra unknown fields ---

    def test_extra_fields_ignored(self):
        """Unknown fields should be silently ignored."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "hacker_field": "should_be_ignored",
            "admin": True,
        })
        assert resp.status_code == 201

    # --- completely invalid payloads ---

    def test_empty_json_body(self):
        """Empty JSON body should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={})
        assert resp.status_code == 422

    def test_all_required_fields_null(self):
        """All required fields set to null should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": None,
            "outcome": None,
            "source": None,
        })
        assert resp.status_code == 422


# ===================================================================
#  4. PUT /api/v1/negative-results/{id} — UpdateNegativeResultRequest
# ===================================================================

class TestNegativeResultUpdateFuzzing:
    """Fuzzing tests for PUT /api/v1/negative-results/{id}."""

    def test_update_claim_exceeds_max_length(self):
        """Claim over 2000 chars in update should be rejected."""
        client = _nr_client()
        entry = _create_nr(client)
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "claim": "z" * 2001,
        })
        assert resp.status_code == 422

    def test_update_confidence_out_of_range(self):
        """Confidence outside 0-1 in update should be rejected."""
        client = _nr_client()
        entry = _create_nr(client)
        for bad_val in [-0.1, 1.1, 100.0, -999.0]:
            resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
                "confidence": bad_val,
            })
            assert resp.status_code == 422, f"Bad confidence accepted: {bad_val}"

    def test_update_confidence_valid_boundaries(self):
        """Confidence at boundaries should be accepted in update."""
        client = _nr_client()
        entry = _create_nr(client)
        for good_val in [0.0, 0.5, 1.0]:
            resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
                "confidence": good_val,
            })
            assert resp.status_code == 200, f"Good confidence rejected: {good_val}"
            assert resp.json()["confidence"] == good_val

    def test_update_source_invalid(self):
        """Invalid source in update should be rejected."""
        client = _nr_client()
        entry = _create_nr(client)
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "source": "INVALID",
        })
        assert resp.status_code == 422

    def test_update_verification_status_invalid(self):
        """Invalid verification_status should be rejected (pattern constraint)."""
        client = _nr_client()
        entry = _create_nr(client)
        for bad_status in ["CONFIRMED", "yes", "true", "pending"]:
            resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
                "verification_status": bad_status,
            })
            assert resp.status_code == 422, f"Invalid status accepted: {bad_status}"

    def test_update_verification_status_valid(self):
        """Valid verification_status values should be accepted."""
        client = _nr_client()
        for status in ["unverified", "confirmed", "rejected", "ambiguous"]:
            entry = _create_nr(client)
            resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
                "verification_status": status,
            })
            assert resp.status_code == 200, f"Valid status rejected: {status}"
            assert resp.json()["verification_status"] == status

    def test_update_failure_category_invalid(self):
        """Invalid failure_category in update should be rejected."""
        client = _nr_client()
        entry = _create_nr(client)
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "failure_category": "not_a_category",
        })
        assert resp.status_code == 422

    def test_update_with_sql_injection_in_claim(self):
        """SQL injection in updated claim should be stored safely."""
        client = _nr_client()
        entry = _create_nr(client)
        injection = "'; DROP TABLE negative_result; --"
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "claim": injection,
        })
        assert resp.status_code == 200
        assert resp.json()["claim"] == injection

    def test_update_with_xss_in_outcome(self):
        """XSS payload in updated outcome should be stored as-is."""
        client = _nr_client()
        entry = _create_nr(client)
        xss = "<script>alert('pwned')</script>"
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "outcome": xss,
        })
        assert resp.status_code == 200
        assert resp.json()["outcome"] == xss

    def test_update_nonexistent_id(self):
        """PUT to nonexistent ID should return 404."""
        client = _nr_client()
        resp = client.put("/api/v1/negative-results/fake-id-999", json={
            "confidence": 0.9,
        })
        assert resp.status_code == 404

    def test_update_empty_body(self):
        """Empty update body should succeed (no fields to update)."""
        client = _nr_client()
        entry = _create_nr(client)
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={})
        assert resp.status_code == 200
        # Original values preserved
        assert resp.json()["claim"] == entry["claim"]

    def test_update_extra_unknown_fields(self):
        """Unknown fields in update should be ignored."""
        client = _nr_client()
        entry = _create_nr(client)
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "confidence": 0.9,
            "not_a_real_field": "ignored",
        })
        assert resp.status_code == 200
        assert resp.json()["confidence"] == 0.9

    def test_update_conditions_deeply_nested(self):
        """Deeply nested conditions in update should be stored."""
        client = _nr_client()
        entry = _create_nr(client)
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "deep_value"}}}}}}
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "conditions": deep,
        })
        assert resp.status_code == 200
        assert resp.json()["conditions"]["a"]["b"]["c"]["d"]["e"]["f"] == "deep_value"

    def test_update_unicode_in_verified_by(self):
        """Unicode in verified_by field should be accepted."""
        client = _nr_client()
        entry = _create_nr(client)
        korean_name = "\uae40\uc7a5\uadfc"  # Korean name (BMP characters, no surrogates)
        resp = client.put(f"/api/v1/negative-results/{entry['id']}", json={
            "verified_by": korean_name,
            "verification_status": "confirmed",
        })
        assert resp.status_code == 200
        assert resp.json()["verified_by"] == korean_name


# ===================================================================
#  5. Cross-cutting / Structural fuzzing
# ===================================================================

class TestStructuralFuzzing:
    """Tests for structural edge cases across endpoints."""

    def test_workflow_create_with_numeric_query(self):
        """Numeric value for query field should be coerced to string or rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": 12345,
        })
        # Pydantic v2 coerces int to str in strict=False mode (default)
        # Either 200 (coerced) or 422 (strict) is acceptable
        assert resp.status_code in (200, 422)

    def test_workflow_create_with_boolean_template(self):
        """Boolean for template should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": True,
            "query": "test",
        })
        assert resp.status_code == 422

    def test_nr_create_with_list_for_claim(self):
        """List for claim field should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": ["not", "a", "string"],
            "outcome": "result",
            "source": "internal",
        })
        assert resp.status_code == 422

    def test_nr_create_with_dict_for_outcome(self):
        """Dict for outcome field should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test",
            "outcome": {"nested": "object"},
            "source": "internal",
        })
        assert resp.status_code == 422

    def test_nr_create_confidence_nan(self):
        """NaN for confidence should be rejected."""
        client = _nr_client()
        # float("nan") is not JSON-serializable, so send raw JSON with NaN literal
        # JSON spec does not support NaN; use a string representation or just test
        # that a non-numeric string is rejected instead
        resp = client.post(
            "/api/v1/negative-results",
            content='{"claim": "test", "outcome": "result", "source": "internal", "confidence": "NaN"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_workflow_seed_papers_wrong_type(self):
        """String instead of list for seed_papers should be rejected."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "seed_papers": "not_a_list",
        })
        assert resp.status_code == 422

    def test_workflow_seed_papers_nested_lists(self):
        """Nested lists in seed_papers should be rejected (items must be str)."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1",
            "query": "test",
            "seed_papers": [["nested", "list"]],
        })
        assert resp.status_code == 422

    def test_nr_implications_wrong_type(self):
        """String instead of list for implications should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "implications": "not_a_list",
        })
        assert resp.status_code == 422

    def test_nr_conditions_wrong_type(self):
        """String instead of dict for conditions should be rejected."""
        client = _nr_client()
        resp = client.post("/api/v1/negative-results", json={
            "claim": "test", "outcome": "result", "source": "internal",
            "conditions": "not_a_dict",
        })
        assert resp.status_code == 422

    def test_workflow_budget_null(self):
        """null budget should use default."""
        client = _wf_client()
        resp = client.post("/api/v1/workflows", json={
            "template": "W1", "query": "test", "budget": None,
        })
        # Pydantic should either use default or reject null for float field
        # With default=5.0, None may be rejected or coerced
        assert resp.status_code in (200, 422)

    def test_intervene_with_all_valid_actions(self):
        """All valid Literal actions should be accepted on PENDING workflow."""
        client = _wf_client()
        # "cancel" works from PENDING; pause/resume need RUNNING state
        wf = _create_wf(client)
        resp = client.post(f"/api/v1/workflows/{wf['workflow_id']}/intervene", json={
            "action": "cancel",
        })
        assert resp.status_code == 200
        assert resp.json()["new_state"] == "CANCELLED"

    def test_double_cancel_returns_conflict(self):
        """Cancelling an already-cancelled workflow should return 409."""
        client = _wf_client()
        wf = _create_wf(client)
        wf_id = wf["workflow_id"]
        # First cancel
        resp1 = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
            "action": "cancel",
        })
        assert resp1.status_code == 200
        # Second cancel -- CANCELLED is terminal, so this should fail
        resp2 = client.post(f"/api/v1/workflows/{wf_id}/intervene", json={
            "action": "cancel",
        })
        assert resp2.status_code == 409


# ===================================================================
#  CLI runner
# ===================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
