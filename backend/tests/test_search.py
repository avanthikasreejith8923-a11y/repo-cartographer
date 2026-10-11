"""Unit tests for search service, RRF fusion, and GitHub permalink generation."""

import uuid

import pytest

from app.services.search import (
    build_github_permalink,
    reciprocal_rank_fusion,
)


def test_reciprocal_rank_fusion_empty():
    assert reciprocal_rank_fusion([], []) == []


def test_reciprocal_rank_fusion_disjoint():
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    ranked = reciprocal_rank_fusion([id1], [id2], k=60)
    assert len(ranked) == 2
    # Both ranked 1st in their respective lists: score = 1 / (60 + 1)
    expected_score = 1.0 / 61.0
    assert pytest.approx(ranked[0][1]) == expected_score
    assert pytest.approx(ranked[1][1]) == expected_score


def test_reciprocal_rank_fusion_overlapping_boost():
    id_both = uuid.uuid4()
    id_sem_only = uuid.uuid4()
    id_kw_only = uuid.uuid4()

    # id_both is rank 1 in semantic and rank 1 in keyword
    ranked = reciprocal_rank_fusion(
        semantic_ids=[id_both, id_sem_only],
        keyword_ids=[id_both, id_kw_only],
        k=60,
    )
    assert len(ranked) == 3
    # id_both must be ranked first because it appears in both lists
    assert ranked[0][0] == id_both
    expected_both_score = (1.0 / (60 + 1)) + (1.0 / (60 + 1))
    assert pytest.approx(ranked[0][1]) == expected_both_score

    # id_sem_only and id_kw_only are rank 2
    expected_rank2_score = 1.0 / (60 + 2)
    assert pytest.approx(ranked[1][1]) == expected_rank2_score
    assert pytest.approx(ranked[2][1]) == expected_rank2_score


def test_build_github_permalink_single_line():
    url = build_github_permalink(
        full_name="octocat/Hello-World",
        commit_sha="7a993a78c045699a3c06e387b5cf159a5461156d",
        path="src/main.py",
        start_line=15,
        end_line=15,
    )
    assert url == "https://github.com/octocat/Hello-World/blob/7a993a78c045699a3c06e387b5cf159a5461156d/src/main.py#L15"


def test_build_github_permalink_multiline_range():
    url = build_github_permalink(
        full_name="octocat/Hello-World",
        commit_sha="7a993a78c045699a3c06e387b5cf159a5461156d",
        path="/src/utils/math.py",
        start_line=10,
        end_line=45,
    )
    # Should strip leading slash and create range #L10-L45
    assert url == "https://github.com/octocat/Hello-World/blob/7a993a78c045699a3c06e387b5cf159a5461156d/src/utils/math.py#L10-L45"


def test_build_github_permalink_default_branch_when_sha_none():
    url = build_github_permalink(
        full_name="facebook/react",
        commit_sha=None,
        path="packages/react/index.js",
        start_line=1,
        end_line=5,
    )
    assert url == "https://github.com/facebook/react/blob/main/packages/react/index.js#L1-L5"
