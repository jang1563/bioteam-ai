"""Tests for Manuscript Studio session API."""

import base64
import io
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tests.api_testkit import build_router_client, cleanup_sqlite_path, make_temp_sqlite_url

_DATABASE_URL, _TEST_DB_PATH = make_temp_sqlite_url("bioteam_manuscript_api")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app.agents.registry import create_registry
from app.api.v1.manuscript import router as manuscript_router
from app.api.v1.manuscript import set_auditor_agent as set_manuscript_auditor
from app.api.v1.workflows import router as workflows_router
from app.api.v1.workflows import set_dependencies as set_workflow_dependencies
from app.db.database import create_db_and_tables
from app.db.database import engine as db_engine
from app.llm.mock_layer import MockLLMLayer
from app.models.integrity import AuditFinding
from app.models.workflow import WorkflowInstance
from app.workflows.engine import WorkflowEngine
from fastapi.testclient import TestClient
from sqlmodel import Session


def _build_client() -> TestClient:
    create_db_and_tables()
    mock = MockLLMLayer()
    registry = create_registry(mock)
    engine = WorkflowEngine()
    set_workflow_dependencies(registry, engine)
    set_manuscript_auditor(registry.get("data_integrity_auditor"))
    return build_router_client(manuscript_router, workflows_router)


@pytest.fixture
def client():
    with _build_client() as test_client:
        yield test_client
    db_engine.dispose()
    cleanup_sqlite_path(_TEST_DB_PATH)


def _insert_workflow(instance: WorkflowInstance) -> WorkflowInstance:
    with Session(db_engine) as session:
        session.add(instance)
        session.commit()
        session.refresh(instance)
        session.expunge(instance)
    return instance


def _insert_finding(finding: AuditFinding) -> AuditFinding:
    with Session(db_engine) as session:
        session.add(finding)
        session.commit()
        session.refresh(finding)
        session.expunge(finding)
    return finding


def _story_frame(frame_id: str, narrative_type: str, hook: str) -> dict:
    return {
        "frame_id": frame_id,
        "narrative_type": narrative_type,
        "hook": hook,
        "central_tension": "Expected mechanism differs from the observed adaptation.",
        "core_claim": "This manuscript identifies the main biological driver of the phenotype.",
        "supporting_findings": ["RNA-seq shift in erythroid genes", "Perturbation rescues the phenotype"],
        "figure_sequence": ["Phenotype overview", "Mechanistic assay", "Validation experiment"],
        "target_tier": "specialty",
        "novelty_rationale": "The paper reframes a known phenomenon with a clearer mechanistic anchor.",
        "blind_spots": ["Limited human validation"],
        "impact_score": 0.74,
        "version": 1,
        "provenance": "llm",
    }


def test_create_and_list_manuscript_sessions(client):
    response = client.post("/api/v1/manuscript/sessions", json={
        "title": "Spaceflight anemia manuscript",
        "query": "How should we frame the erythroid adaptation story in microgravity?",
        "notes": "Need a strong mechanism-first story before drafting.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Spaceflight anemia manuscript"
    assert data["phase"] == "collect_inputs"
    assert data["completion_state"] == "empty"
    assert data["linked_workflows"] == {}

    list_resp = client.get("/api/v1/manuscript/sessions")
    assert list_resp.status_code == 200
    ids = {item["id"] for item in list_resp.json()}
    assert data["id"] in ids


def test_linking_workflows_aggregates_manuscript_outputs(client):

    w11 = _insert_workflow(
        WorkflowInstance(
            template="W11",
            query="spaceflight anemia framing",
            state="COMPLETED",
            session_manifest={
                "frame_options": {
                    "frames": [
                        _story_frame("SF-001", "mechanism_discovery", "A mechanism-first frame."),
                        _story_frame("SF-002", "clinical_implication", "A translational frame."),
                    ],
                    "selected_frame_id": "SF-001",
                    "generation_context": "spaceflight anemia",
                    "generation_mode": "llm",
                    "fallback_reason": None,
                },
                "selected_story_frame": _story_frame("SF-001", "mechanism_discovery", "A mechanism-first frame."),
            },
        )
    )
    w8 = _insert_workflow(
        WorkflowInstance(
            template="W8",
            query="spaceflight anemia review",
            state="COMPLETED",
            rcmxt_scores=[
                {
                    "claim": "Gene X drives erythroid adaptation in microgravity.",
                    "R": 0.82,
                    "C": 0.77,
                    "M": 0.73,
                    "X": 0.68,
                    "T": 0.71,
                    "composite": 0.742,
                    "sources": ["10.1000/test-doi"],
                }
            ],
            session_manifest={
                "peer_review_report": {
                    "claims_extracted": [
                        {
                            "claim_text": "Gene X drives erythroid adaptation in microgravity.",
                            "section": "Results",
                            "claim_type": "main_finding",
                            "supporting_refs": ["10.1000/test-doi"],
                            "verbatim_quote": "Gene X increased during exposure.",
                            "confidence": 0.91,
                        }
                    ],
                    "synthesis": {
                        "summary_assessment": "Promising but vulnerable to reviewer questions.",
                        "decision": "major_revision",
                        "decision_reasoning": "Controls and novelty framing need work.",
                        "comments": [
                            {
                                "category": "major",
                                "section": "Methods",
                                "comment": "Controls are underspecified for the perturbation experiment.",
                                "evidence_basis": "The methods section omits matched ground controls.",
                            }
                        ],
                    },
                    "novelty_assessment": {
                        "novelty_score": 0.58,
                        "already_established": [],
                        "unique_contributions": ["Links erythroid remodeling to a specific regulator."],
                        "landmark_papers_missing": ["Compare against PMID 12345 before submission."],
                        "novelty_recommendation": "Frame the manuscript as a mechanistic clarification.",
                    },
                    "methodology_assessment": {
                        "study_design_critique": "The overall design is plausible but control selection is thin.",
                        "statistical_methods": "Mixed-effects analysis is appropriate.",
                        "controls_adequacy": "Ground controls are not described clearly enough.",
                        "sample_size_assessment": "Sample size is borderline for subgroup analyses.",
                        "potential_biases": ["Potential batch effects between flights."],
                        "reproducibility_concerns": ["Protocol details are too sparse for exact replication."],
                        "domain_specific_issues": [],
                        "strengths": ["Multi-modal readout"],
                        "overall_methodology_score": 0.61,
                    },
                }
            },
        )
    )
    w7 = _insert_workflow(
        WorkflowInstance(
            template="W7",
            query="spaceflight anemia submission checks",
            state="COMPLETED",
            session_manifest={
                "integrity_report": {
                    "total_findings": 1,
                    "findings_by_severity": {"warning": 1},
                    "findings_by_category": {"gene_name_error": 1},
                    "overall_level": "minor_issues",
                    "findings": [
                        {
                            "title": "Potential gene naming issue",
                            "category": "gene_name_error",
                            "severity": "warning",
                            "description": "SEPT2 may be misread as a spreadsheet date.",
                            "suggestion": "Use HGNC-approved symbol formatting.",
                        }
                    ],
                }
            },
        )
    )
    _insert_finding(
        AuditFinding(
            workflow_id=w7.id,
            category="gene_name_error",
            severity="warning",
            title="Potential gene naming issue",
            description="SEPT2 may be misread as a spreadsheet date.",
            suggestion="Use HGNC-approved symbol formatting.",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "title": "Microgravity anemia paper",
        "query": "Build a defensible manuscript around erythroid adaptation in microgravity.",
    })
    assert create_resp.status_code == 200
    manuscript_session_id = create_resp.json()["id"]

    for workflow_id in (w11.id, w8.id, w7.id):
        link_resp = client.post(
            f"/api/v1/manuscript/sessions/{manuscript_session_id}/link-workflow",
            json={"workflow_id": workflow_id},
        )
        assert link_resp.status_code == 200

    get_resp = client.get(f"/api/v1/manuscript/sessions/{manuscript_session_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert data["phase"] == "outline_ready"
    assert data["completion_state"] == "ready"
    assert data["selected_frame_id"] == "SF-001"
    assert data["selected_frame"]["frame_id"] == "SF-001"
    assert data["linked_workflows"]["W11"] == w11.id
    assert data["linked_workflows"]["W8"] == w8.id
    assert data["linked_workflows"]["W7"] == w7.id
    assert len(data["claim_map"]) == 1
    assert data["claim_map"][0]["risk_level"] == "low"
    assert len(data["reviewer_risks"]) >= 3
    assert data["reviewer_risk_report"]["report_type"] == "ReviewerRiskReport"
    assert data["reviewer_risk_report"]["version"] == "v1"
    assert data["reviewer_risk_report"]["maturity"] == "validated_core"
    assert data["reviewer_risk_report"]["run_metadata"]["workflow_id"] == w8.id
    assert len(data["integrity_flags"]) >= 1
    assert data["integrity_audit_report"]["report_type"] == "IntegrityAuditReport"
    assert data["integrity_audit_report"]["version"] == "v1"
    assert data["integrity_audit_report"]["maturity"] == "validated_core"
    assert data["integrity_audit_report"]["run_metadata"]["workflow_id"] == w7.id
    assert len(data["outline"]) >= 3


def test_defense_brief_exports_markdown_summary(client):
    w11 = _insert_workflow(
        WorkflowInstance(
            template="W11",
            query="defense brief framing",
            state="COMPLETED",
            session_manifest={
                "frame_options": {
                    "frames": [_story_frame("SF-001", "mechanism_discovery", "A mechanism-first frame.")],
                    "selected_frame_id": "SF-001",
                    "generation_context": "defense brief",
                    "generation_mode": "llm",
                    "fallback_reason": None,
                },
                "selected_story_frame": _story_frame("SF-001", "mechanism_discovery", "A mechanism-first frame."),
            },
        )
    )
    w8 = _insert_workflow(
        WorkflowInstance(
            template="W8",
            query="defense brief review",
            state="COMPLETED",
            rcmxt_scores=[
                {
                    "claim": "Gene X drives erythroid adaptation in microgravity.",
                    "R": 0.82,
                    "C": 0.77,
                    "M": 0.73,
                    "X": 0.68,
                    "T": 0.71,
                    "composite": 0.742,
                    "sources": ["10.1000/test-doi"],
                }
            ],
            session_manifest={
                "peer_review_report": {
                    "claims_extracted": [],
                    "synthesis": {
                        "comments": [
                            {
                                "category": "major",
                                "section": "Methods",
                                "comment": "Controls remain underspecified for the perturbation experiment.",
                                "evidence_basis": "Ground controls are not described clearly enough.",
                            }
                        ],
                    },
                    "novelty_assessment": {"landmark_papers_missing": []},
                    "methodology_assessment": {"potential_biases": [], "reproducibility_concerns": []},
                }
            },
        )
    )
    w7 = _insert_workflow(
        WorkflowInstance(
            template="W7",
            query="defense brief audit",
            state="COMPLETED",
            session_manifest={},
        )
    )
    _insert_finding(
        AuditFinding(
            workflow_id=w7.id,
            category="gene_name_error",
            severity="warning",
            title="Potential gene naming issue",
            description="SEPT2 may be misread as a spreadsheet date.",
            suggestion="Use HGNC-approved symbol formatting.",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "title": "Microgravity anemia defense brief",
        "query": "Build a defensible manuscript around erythroid adaptation in microgravity.",
        "notes": "Focus on a mechanism-first framing.",
        "target_journal": "Nature Communications",
    })
    manuscript_session_id = create_resp.json()["id"]

    for workflow_id in (w11.id, w8.id, w7.id):
        link_resp = client.post(
            f"/api/v1/manuscript/sessions/{manuscript_session_id}/link-workflow",
            json={"workflow_id": workflow_id},
        )
        assert link_resp.status_code == 200

    export_resp = client.get(f"/api/v1/manuscript/sessions/{manuscript_session_id}/defense-brief")
    assert export_resp.status_code == 200
    data = export_resp.json()
    assert data["filename"].endswith("_defense_brief.md")
    assert "# Microgravity anemia defense brief" in data["markdown"]
    assert "## Story Frame" in data["markdown"]
    assert "## Claim Map" in data["markdown"]
    assert "## Reviewer Risks" in data["markdown"]
    assert "## Submission Checks" in data["markdown"]
    assert "Potential gene naming issue" in data["markdown"]

    print_resp = client.get(f"/api/v1/manuscript/sessions/{manuscript_session_id}/defense-brief/print")
    assert print_resp.status_code == 200
    print_data = print_resp.json()
    assert print_data["filename"].endswith("_defense_brief.html")
    assert "<title>Microgravity anemia defense brief" in print_data["html"]
    assert "<h2>Claim Map</h2>" in print_data["html"]
    assert "<h2>Reviewer Risks</h2>" in print_data["html"]
    assert "Potential gene naming issue" in print_data["html"]
    assert "window.print()" in print_data["html"]

    docx_resp = client.get(f"/api/v1/manuscript/sessions/{manuscript_session_id}/defense-brief/docx")
    assert docx_resp.status_code == 200
    docx_data = docx_resp.json()
    assert docx_data["filename"].endswith("_defense_brief.docx")
    payload = base64.b64decode(docx_data["content_base64"])
    assert payload[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "Microgravity anemia defense brief" in xml
    assert "Claim Map" in xml
    assert "Reviewer Risks" in xml
    assert "Potential gene naming issue" in xml


def test_select_frame_updates_session_outline(client):

    w11 = _insert_workflow(
        WorkflowInstance(
            template="W11",
            query="story frame selection test",
            state="WAITING_HUMAN",
            session_manifest={
                "frame_options": {
                    "frames": [
                        _story_frame("SF-001", "mechanism_discovery", "Mechanism-first hook."),
                        _story_frame("SF-002", "negative_reframe", "Negative result reframe hook."),
                    ],
                    "selected_frame_id": None,
                    "generation_context": "story frame selection test",
                    "generation_mode": "llm",
                    "fallback_reason": None,
                }
            },
        )
    )

    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Pick the strongest frame for an unexpected null result.",
    })
    manuscript_session_id = create_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/link-workflow",
        json={"workflow_id": w11.id},
    )
    assert link_resp.status_code == 200
    assert link_resp.json()["phase"] == "select_frame"

    select_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/select-frame",
        json={"frame_id": "SF-002"},
    )
    assert select_resp.status_code == 200
    data = select_resp.json()
    assert data["selected_frame_id"] == "SF-002"
    assert data["selected_frame"]["frame_id"] == "SF-002"
    assert data["outline"][0]["title"] == "Narrative Anchor"


def test_run_story_frames_creates_and_links_w11_workflow(client):
    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Generate a defensible mechanism-first frame for spaceflight anemia.",
        "notes": "Prefer a specialty-journal framing.",
    })
    assert create_resp.status_code == 200
    manuscript_session_id = create_resp.json()["id"]

    run_resp = client.post(f"/api/v1/manuscript/sessions/{manuscript_session_id}/run-story-frames")
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert "W11" in data["linked_workflows"]
    assert any(item["stage"] == "story_frames" and item["status"] in {"running", "waiting_human"} for item in data["stage_statuses"])

    workflow_id = data["linked_workflows"]["W11"]
    workflow_resp = client.get(f"/api/v1/workflows/{workflow_id}")
    assert workflow_resp.status_code == 200
    assert workflow_resp.json()["template"] == "W11"


def test_run_reviewer_risks_creates_and_links_w8_workflow(client):
    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Review this manuscript for likely reviewer concerns before submission.",
        "notes": "Focus on novelty framing and control adequacy.",
    })
    assert create_resp.status_code == 200
    manuscript_session_id = create_resp.json()["id"]

    pdf_path = Path(tempfile.gettempdir()) / "manuscript-session-reviewer-risks.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% reviewer-risks fixture\n")

    async def _fake_create_workflow(request):
        instance = _insert_workflow(
            WorkflowInstance(
                template=request.template,
                query=request.query,
                state="RUNNING",
                pdf_path=request.pdf_path,
            )
        )

        class _Response:
            workflow_id = instance.id
            template = instance.template
            state = instance.state
            query = instance.query

        return _Response()

    with patch("app.api.v1.workflows.create_workflow", side_effect=_fake_create_workflow):
        run_resp = client.post(
            f"/api/v1/manuscript/sessions/{manuscript_session_id}/run-reviewer-risks",
            json={"pdf_path": str(pdf_path)},
        )

    assert run_resp.status_code == 200
    data = run_resp.json()
    assert "W8" in data["linked_workflows"]
    assert any(
        item["stage"] == "reviewer_risks" and item["status"] in {"running", "partial", "ready", "waiting_human"}
        for item in data["stage_statuses"]
    )

    workflow_id = data["linked_workflows"]["W8"]
    with Session(db_engine) as session:
        workflow = session.get(WorkflowInstance, workflow_id)
        assert workflow is not None
        assert workflow.template == "W8"
        assert workflow.pdf_path == str(pdf_path.resolve(strict=False))


def test_upload_reviewer_paper_stores_temp_file_and_links_w8(client):
    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Upload a manuscript and start reviewer-risk analysis.",
    })
    assert create_resp.status_code == 200
    manuscript_session_id = create_resp.json()["id"]
    expected_bytes = b"%PDF-1.4\n% uploaded reviewer paper\n"

    async def _fake_create_workflow(request):
        saved_path = Path(request.pdf_path)
        assert saved_path.exists()
        assert saved_path.read_bytes() == expected_bytes
        temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
        assert temp_root in saved_path.parents

        instance = _insert_workflow(
            WorkflowInstance(
                template=request.template,
                query=request.query,
                state="RUNNING",
                pdf_path=request.pdf_path,
            )
        )

        return SimpleNamespace(
            workflow_id=instance.id,
            template=instance.template,
            state=instance.state,
            query=instance.query,
        )

    with patch("app.api.v1.workflows.create_workflow", side_effect=_fake_create_workflow):
        upload_resp = client.post(
            f"/api/v1/manuscript/sessions/{manuscript_session_id}/upload-reviewer-paper",
            files={"file": ("uploaded_paper.pdf", expected_bytes, "application/pdf")},
        )

    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert "W8" in data["linked_workflows"]
    workflow_id = data["linked_workflows"]["W8"]
    with Session(db_engine) as session:
        workflow = session.get(WorkflowInstance, workflow_id)
        assert workflow is not None
        assert workflow.pdf_path is not None
        assert Path(workflow.pdf_path).exists()


def test_resume_reviewer_risks_resumes_waiting_w8(client):
    w8 = _insert_workflow(
        WorkflowInstance(
            template="W8",
            query="peer review continuation",
            state="WAITING_HUMAN",
            current_step="HUMAN_CHECKPOINT",
        )
    )
    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Resume the W8 peer review synthesis after reviewer approval.",
    })
    manuscript_session_id = create_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/link-workflow",
        json={"workflow_id": w8.id},
    )
    assert link_resp.status_code == 200

    async def _fake_resume_workflow(workflow_id, request):
        with Session(db_engine) as session:
            workflow = session.get(WorkflowInstance, workflow_id)
            assert workflow is not None
            workflow.state = "RUNNING"
            session.add(workflow)
            session.commit()

        return SimpleNamespace(
            workflow_id=workflow_id,
            new_state="RUNNING",
            budget_remaining=5.0,
            detail="Workflow resumed.",
        )

    with patch("app.api.v1.resume.resume_workflow", side_effect=_fake_resume_workflow):
        resume_resp = client.post(
            f"/api/v1/manuscript/sessions/{manuscript_session_id}/resume-reviewer-risks",
        )

    assert resume_resp.status_code == 200
    data = resume_resp.json()
    assert any(
        item["stage"] == "reviewer_risks" and item["status"] == "running"
        for item in data["stage_statuses"]
    )

    with Session(db_engine) as session:
        workflow = session.get(WorkflowInstance, w8.id)
        assert workflow is not None
        assert workflow.state == "RUNNING"


def test_run_full_submission_audit_creates_and_links_w7(client):
    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Run a full submission audit for this manuscript.",
        "draft_text": "Gene 2-Sep increased across replicates in the draft results section.",
        "notes": "Check naming consistency and any reviewer-visible integrity issues.",
        "target_journal": "Nature Communications",
    })
    assert create_resp.status_code == 200
    manuscript_session_id = create_resp.json()["id"]

    async def _fake_create_workflow(request):
        assert request.template == "W7"
        assert "Run a full biology submission audit" in request.query
        assert "Nature Communications" in request.query

        instance = _insert_workflow(
            WorkflowInstance(
                template=request.template,
                query=request.query,
                state="RUNNING",
            )
        )

        return SimpleNamespace(
            workflow_id=instance.id,
            template=instance.template,
            state=instance.state,
            query=instance.query,
        )

    with patch("app.api.v1.workflows.create_workflow", side_effect=_fake_create_workflow):
        run_resp = client.post(
            f"/api/v1/manuscript/sessions/{manuscript_session_id}/run-full-submission-audit",
        )

    assert run_resp.status_code == 200
    data = run_resp.json()
    assert "W7" in data["linked_workflows"]
    assert any(
        item["stage"] == "submission_checks" and item["status"] == "running"
        for item in data["stage_statuses"]
    )

    workflow_id = data["linked_workflows"]["W7"]
    with Session(db_engine) as session:
        workflow = session.get(WorkflowInstance, workflow_id)
        assert workflow is not None
        assert workflow.template == "W7"


def test_approve_story_scope_injects_target_tier_into_waiting_w11(client):
    w11 = _insert_workflow(
        WorkflowInstance(
            template="W11",
            query="spaceflight anemia framing",
            state="WAITING_HUMAN",
            current_step="SCOPE",
            session_manifest={
                "w11_phase": "awaiting_scope",
                "scope_summary": "Confirm scope and target tier before generating frames.",
            },
        )
    )

    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Generate the strongest story for a spaceflight anemia paper.",
    })
    manuscript_session_id = create_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/link-workflow",
        json={"workflow_id": w11.id},
    )
    assert link_resp.status_code == 200

    approve_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/approve-story-scope",
        json={"target_tier": "grant"},
    )
    assert approve_resp.status_code == 200
    data = approve_resp.json()
    assert any(
        item["stage"] == "story_frames" and item["status"] in {"running", "waiting_human"}
        for item in data["stage_statuses"]
    )

    with Session(db_engine) as session:
        refreshed = session.get(WorkflowInstance, w11.id)
        assert refreshed is not None
        assert any("target_tier: grant" in note.get("text", "") for note in refreshed.injected_notes)


def test_select_frame_injects_selection_into_waiting_w11(client):
    w11 = _insert_workflow(
        WorkflowInstance(
            template="W11",
            query="story frame selection test",
            state="WAITING_HUMAN",
            current_step="HUMAN_CHECKPOINT",
            session_manifest={
                "w11_phase": "awaiting_selection",
                "frame_options": {
                    "frames": [
                        _story_frame("SF-001", "mechanism_discovery", "Mechanism-first hook."),
                        _story_frame("SF-002", "negative_reframe", "Negative result reframe hook."),
                    ],
                    "selected_frame_id": None,
                    "generation_context": "story frame selection test",
                    "generation_mode": "llm",
                    "fallback_reason": None,
                },
            },
        )
    )

    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Pick the strongest frame for an unexpected null result.",
    })
    manuscript_session_id = create_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/link-workflow",
        json={"workflow_id": w11.id},
    )
    assert link_resp.status_code == 200

    select_resp = client.post(
        f"/api/v1/manuscript/sessions/{manuscript_session_id}/select-frame",
        json={"frame_id": "SF-002"},
    )
    assert select_resp.status_code == 200
    data = select_resp.json()
    assert data["selected_frame_id"] == "SF-002"
    assert any(
        item["stage"] == "story_frames" and item["status"] in {"running", "ready", "waiting_human"}
        for item in data["stage_statuses"]
    )

    with Session(db_engine) as session:
        refreshed = session.get(WorkflowInstance, w11.id)
        assert refreshed is not None
        assert any("selected_frame_id: SF-002" in note.get("text", "") for note in refreshed.injected_notes)


def test_run_submission_checks_populates_integrity_flags_from_session_text(client):
    create_resp = client.post("/api/v1/manuscript/sessions", json={
        "query": "Quickly check this draft before submission.",
        "draft_text": "Gene 2-Sep increased significantly in the manuscript draft, and the notation needs review.",
        "notes": "Make sure spreadsheet-style gene symbol issues are caught before submission.",
    })
    assert create_resp.status_code == 200
    manuscript_session_id = create_resp.json()["id"]

    run_resp = client.post(f"/api/v1/manuscript/sessions/{manuscript_session_id}/run-submission-checks")
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert len(data["integrity_flags"]) >= 1
    assert any(flag["generated_by"] == "manuscript_session:quick_check" for flag in data["integrity_flags"])
    assert data["integrity_audit_report"]["report_type"] == "IntegrityAuditReport"
    assert data["integrity_audit_report"]["maturity"] == "guided_support"
    assert data["integrity_audit_report"]["run_metadata"]["workflow_id"] is None
    assert any(item["stage"] == "submission_checks" and item["status"] == "ready" for item in data["stage_statuses"])
