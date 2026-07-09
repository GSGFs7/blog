import logging
from typing import Dict, List, Optional, TypedDict

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, Min
from pgvector.django import CosineDistance

from api.models import Post, PostChunk
from api.tasks import generate_search_embedding_task

# only `post_search` function is useful
__all__ = ["post_search"]

CONFIDENCE = 0.6
RELATIVE_CUTOFF = 0.3

logger = logging.getLogger(__name__)


class ScoreItem(TypedDict):
    id: int
    score: float


class SearchResult(TypedDict):
    id: int
    hybrid_score: float


def perform_full_text_search(query: str) -> List[ScoreItem]:
    import jieba

    # tokenize query
    tokenized_query = " ".join(jieba.lcut(query, cut_all=True))
    search_query = SearchQuery(tokenized_query, config="simple")

    # perform query
    rows = (
        Post.objects.annotate(score=SearchRank(F("pg_gin_search_vector"), search_query))
        .filter(pg_gin_search_vector=search_query)
        .values("id", "score")
    )

    return [ScoreItem(**r) for r in rows]


def perform_semantic_search(query: str) -> Optional[List[ScoreItem]]:
    # try celery task whether available
    try:
        # TODO: eliminate anti-patterns
        #  celery: Fire and Forget
        query_embedding = generate_search_embedding_task.delay(query).get(timeout=1)
    except Exception as e:
        logger.warning(f"Search embedding task failed or timed out: {e}")
        return None

    # Group by post_id, and calculate the minimum distance
    # to the most matching block for each post.
    rows = list(
        PostChunk.objects.annotate(
            dist=CosineDistance("embedding", query_embedding),
        )
        .filter(dist__lt=CONFIDENCE)
        .values("post_id")
        .annotate(min_dist=Min("dist"))
        .order_by("min_dist")
    )

    return [ScoreItem(id=r["post_id"], score=r["min_dist"]) for r in rows]


# TODO: asynchronization
def post_search(query: str) -> List[SearchResult]:
    vec_candidates = perform_semantic_search(query)
    fts_candidates = perform_full_text_search(query)

    if vec_candidates is None:
        # fallback to pure FTS
        sorted_fts = sorted(fts_candidates, key=lambda x: x["score"], reverse=True)
        return [
            SearchResult(id=item["id"], hybrid_score=item["score"])
            for item in sorted_fts
        ]

    # ranking mapping
    # higher FTS score is better, smaller vector distance is better
    fts_rank = _build_rank_map(fts_candidates, reverse=True)
    vec_rank = _build_rank_map(vec_candidates, reverse=False)

    # merge and remove duplicates
    candidate_ids = set(fts_rank) | set(vec_rank)
    if not candidate_ids:
        return []

    # combined score
    k = 60
    candidates: List[SearchResult] = []
    for cid in candidate_ids:
        # RRF: score = sum(1 / (k + rank))
        score = 0.0
        if cid in fts_rank:
            score += 1.0 / (k + fts_rank[cid])
        if cid in vec_rank:
            score += 1.0 / (k + vec_rank[cid])
        candidates.append(SearchResult(id=cid, hybrid_score=score))

    candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return _apply_relative_cutoff(candidates, RELATIVE_CUTOFF)


# --- helper functions ---


def _build_rank_map(
    items: List[ScoreItem],
    reverse: bool = False,
) -> Dict[int, int]:
    """
    convert search results into a dict of ID -> ranking
    """

    if not items:
        return {}

    sorted_items = sorted(items, key=lambda x: x["score"], reverse=reverse)
    return {
        # start from 1
        item["id"]: i + 1
        for i, item in enumerate(sorted_items)
    }


def _apply_relative_cutoff(
    candidates: List[SearchResult], cutoff: float
) -> List[SearchResult]:
    """
    remove trailing part
    """

    if not candidates:
        return []

    top_score = candidates[0]["hybrid_score"]
    return [c for c in candidates if c["hybrid_score"] >= top_score * cutoff]
