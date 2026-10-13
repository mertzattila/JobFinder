"""Unit tests that run offline (no network, no LLM) using fakes."""

from __future__ import annotations

from jobfinder.config import LLMConfig, NotifierConfig, Secrets, Settings
from jobfinder.models import JobPosting, MatchResult, ScoredJob
from jobfinder.pipeline import Pipeline, keyword_match
from jobfinder.state import SeenStore


def _job(**kw) -> JobPosting:
    base = {"title": "Embedded Intern", "company": "Bosch", "url": "https://x.test/1"}
    base.update(kw)
    return JobPosting(**base)


def test_score_coercion_variants():
    assert MatchResult(score="8/10", summary="s").score == 8
    assert MatchResult(score=8.6, summary="s").score == 9
    assert MatchResult(score=99, summary="s").score == 10
    assert MatchResult(score=-5, summary="s").score == 1


def test_keyword_prefilter():
    kws = ["embedded", "gyakornok"]
    assert keyword_match(_job(title="Embedded SW Intern"), kws)
    assert keyword_match(_job(title="Beágyazott", description="gyakornok pozíció"), kws)
    assert not keyword_match(_job(title="Senior Accountant", description="finance"), kws)


def test_fingerprint_stable_and_deduped():
    a = _job(url="https://x.test/job/")
    b = _job(url="https://x.test/job")  # trailing slash should normalise equal
    assert a.fingerprint == b.fingerprint


def test_seen_store_roundtrip(tmp_path):
    p = tmp_path / "seen.json"
    s = SeenStore(p)
    assert not s.is_seen("abc")
    s.mark_seen("abc")
    s.save()
    assert SeenStore(p).is_seen("abc")


def test_pipeline_dry_run_scores_and_skips_seen(tmp_path, monkeypatch):
    settings = Settings(
        keywords=["embedded"],
        score_threshold=7,
        llm=LLMConfig(provider="gemini"),
        notifier=NotifierConfig(channel="discord"),
        targets=[],
    )
    profile = tmp_path / "profile.md"
    profile.write_text("test profile", encoding="utf-8")
    state = tmp_path / "seen.json"

    pipe = Pipeline(
        settings=settings,
        secrets=Secrets(),
        profile_path=str(profile),
        state_path=str(state),
        dry_run=True,
    )

    jobs = [_job(url="https://x.test/good"), _job(url="https://x.test/bad", title="Finance")]
    monkeypatch.setattr(pipe, "_collect_new_jobs", lambda: [jobs[0]])
    monkeypatch.setattr(
        pipe.matcher, "evaluate", lambda job: MatchResult(score=9, summary="great fit")
    )

    alerted = pipe.run()
    assert len(alerted) == 1
    assert isinstance(alerted[0], ScoredJob)
    assert alerted[0].match.score == 9
    # Job is now marked seen -> a second run collects nothing.
    assert pipe.store.is_seen(jobs[0].fingerprint)
