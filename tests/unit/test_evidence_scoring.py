from app.schemas.evidence import EvidenceScore, EvidenceSource
from app.services.evidence.scoring import EvidenceScorer, select_top_evidence


def create_source(
    *,
    source_type: str = "web",
    source_id: str = "WEB-0123456789ABCDEF",
) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        origin="web",
        title="HTTP/3 and QUIC",
        locator="https://example.com/http3",
        content="HTTP/3 uses QUIC to reduce transport handshake latency.",
        provider="fixture",
        source_type=source_type,  # type: ignore[arg-type]
    )


def test_paper_sources_receive_a_scoring_bonus_over_identical_web_sources() -> None:
    web_source = create_source(source_type="web", source_id="WEB-0123456789ABCDEF")
    paper_source = create_source(source_type="paper", source_id="PAPER-0123456789ABCDEF")

    scores = EvidenceScorer().score(
        query="Compare HTTP/3 QUIC handshake latency",
        sources=[web_source, paper_source],
    )

    web_score, paper_score = scores

    assert round(paper_score.overall - web_score.overall, 4) == 0.1
    assert paper_score.relevance == web_score.relevance
    assert paper_score.content_quality == web_score.content_quality
    assert paper_score.traceability == web_score.traceability


def test_overall_score_stays_within_bounds_for_a_maximal_paper_source() -> None:
    source = EvidenceSource(
        source_id="PAPER-0123456789ABCDEF",
        origin="web",
        title="HTTP/3 and QUIC",
        locator="https://example.com/http3",
        content="HTTP/3 uses QUIC to reduce transport handshake latency. " * 20,
        provider="fixture",
        source_type="paper",
        retrieval_score=1.0,
    )

    score = EvidenceScorer().score(
        query="HTTP/3 QUIC handshake latency",
        sources=[source],
    )[0]

    assert score.overall <= 1.0


def create_score(*, source_id: str, overall: float) -> EvidenceScore:
    return EvidenceScore(
        source_id=source_id,
        relevance=overall,
        content_quality=overall,
        traceability=overall,
        overall=overall,
    )


def test_select_top_evidence_keeps_the_highest_scored_sources() -> None:
    high = create_source(source_id="WEB-0000000000000001")
    medium = create_source(source_id="WEB-0000000000000002")
    low = create_source(source_id="WEB-0000000000000003")
    scores = [
        create_score(source_id="WEB-0000000000000001", overall=0.9),
        create_score(source_id="WEB-0000000000000002", overall=0.5),
        create_score(source_id="WEB-0000000000000003", overall=0.1),
    ]

    selected = select_top_evidence([low, medium, high], scores, limit=2)

    assert selected == [high, medium]


def test_select_top_evidence_is_a_no_op_when_under_the_limit() -> None:
    source = create_source(source_id="WEB-0000000000000001")
    scores = [create_score(source_id="WEB-0000000000000001", overall=0.5)]

    selected = select_top_evidence([source], scores, limit=20)

    assert selected == [source]


def test_select_top_evidence_treats_a_missing_score_as_zero() -> None:
    scored = create_source(source_id="WEB-0000000000000001")
    unscored = create_source(source_id="WEB-0000000000000002")
    scores = [create_score(source_id="WEB-0000000000000001", overall=0.1)]

    selected = select_top_evidence([unscored, scored], scores, limit=1)

    assert selected == [scored]
