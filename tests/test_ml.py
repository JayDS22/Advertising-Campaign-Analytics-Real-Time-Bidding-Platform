import random

from src.ml.recommender import CollaborativeFilteringRecommender, ndcg_at_k
from src.ml.ctr_predictor import CTRPredictor


def test_ndcg_perfect_ranking():
    rels = {"a": 3, "b": 2, "c": 1}
    assert ndcg_at_k(["a", "b", "c"], rels, k=3) == 1.0


def test_ndcg_zero_for_irrelevant():
    assert ndcg_at_k(["x"], {"x": 0}, k=1) == 0.0


def test_recommender_trains_and_recommends():
    random.seed(1)
    interactions = []
    for u in range(40):
        for i in range(8):
            r = 1.0 if (u + i) % 2 == 0 else 0.0
            interactions.append((f"u{u}", f"i{i}", r))
    model = CollaborativeFilteringRecommender(n_factors=8, n_iters=10)
    model.fit(interactions)
    recs = model.recommend("u0", k=3)
    assert len(recs) == 3 and all(isinstance(r[1], float) for r in recs)


def test_ctr_predictor_learns():
    model = CTRPredictor(n_features=2 ** 12)
    pos = {"campaign": "A", "device": "mobile", "geo": "US"}
    neg = {"campaign": "B", "device": "desktop", "geo": "DE"}
    for _ in range(500):
        model.update(pos, 1)
        model.update(neg, 0)
    p_pos = model.predict_proba(pos)
    p_neg = model.predict_proba(neg)
    assert p_pos > 0.7 and p_neg < 0.3
