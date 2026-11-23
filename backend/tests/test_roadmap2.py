"""Analytics and cost estimates."""
import pytest

from app.core.config import settings
from app.services import analytics, seed
from app.models import Approval, Workflow

from tests.test_review_regressions import client_for
from tests.test_roadmap1 import LAPTOP_REQUEST, ROUTINE, _run


def test_overview_numbers_match_the_database(db, users):
    seed.seed_history(db)
    d = client_for("manager").get("/api/analytics/overview?days=365").json()
    wfs = db.query(Workflow).filter(Workflow.org_id == 1).all()
    assert d["volume"]["started"] == len(wfs)
    assert d["volume"]["completed"] == sum(w.status == "completed" for w in wfs)
    human = {a.workflow_id for a in db.query(Approval).filter(Approval.status != "pending")}
    completed = [w for w in wfs if w.status == "completed"]
    assert d["rates"]["automation_pct"] == round(len([w for w in completed if w.id not in human]) / len(completed) * 100, 1)
    assert 0 <= d["rates"]["exception_pct"] <= 100
    assert d["failure_reasons"] and all(r["recovered"] <= r["count"] for r in d["failure_reasons"])
    assert len(d["daily"]) == 30


def test_approval_latency_names_the_slowest_role(db, users):
    seed.seed_history(db)
    lat = client_for("admin").get("/api/analytics/overview?days=365").json()["approval_latency"]
    assert lat["decided"] > 0 and lat["avg_hours"] is not None
    hours = [r["avg_hours"] for r in lat["by_role"]]
    assert hours == sorted(hours, reverse=True) and lat["slowest_role"]["avg_hours"] == hours[0]


def test_window_filters_old_workflows(db, users):
    seed.seed_history(db)
    wide = client_for("admin").get("/api/analytics/overview?days=365").json()["volume"]["started"]
    narrow = client_for("admin").get("/api/analytics/overview?days=1").json()["volume"]["started"]
    assert 0 < narrow < wide


def test_savings_estimate_is_arithmetic_on_stated_assumptions(monkeypatch):
    monkeypatch.setitem(settings.roi, "manual_minutes_per_request", 60)
    monkeypatch.setitem(settings.roi, "hourly_cost", 100)
    monkeypatch.setitem(settings.roi, "human_review_minutes", 6)
    monkeypatch.setitem(settings.roi, "llm_call_cost", 2)
    monkeypatch.setitem(settings.roi, "tool_call_cost", 1)
    e = analytics.estimate_savings(completed=10, llm_calls=10, tool_calls=40, human_reviews=5)
    assert e["manual_cost"] == 1000 and e["ai_cost"] == 20 and e["api_cost"] == 40 and e["human_cost"] == 50
    assert e["total_cost"] == 110 and e["savings"] == 890 and e["hours_saved"] == 9.5
    assert e["assumptions"]["hourly_cost"] == 100  # the assumptions always travel with the figures


def test_per_workflow_cost_only_counts_savings_for_completed_work(db, users):
    done = _run(db, users, ROUTINE)
    waiting = _run(db, users, LAPTOP_REQUEST)
    a = client_for("manager").get(f"/api/workflows/{done.id}/cost").json()
    b = client_for("manager").get(f"/api/workflows/{waiting.id}/cost").json()
    assert a["counted_as_saving"] and a["tool_calls"] > 0 and a["savings"] > 0
    assert not b["counted_as_saving"] and b["savings"] <= 0


def test_requesters_cannot_read_analytics_or_other_peoples_costs(db, users):
    wf = _run(db, users, ROUTINE, who="karthik")
    r = client_for("requester")
    assert r.get("/api/analytics/overview").status_code == 403
    assert r.get(f"/api/workflows/{wf.id}/cost").status_code == 404
    assert client_for("manager").get("/api/analytics/overview?days=0").status_code == 422
