from src.experimentation.ab_test import ABTest, BenjaminiHochberg
from src.experimentation.thompson_sampling import ThompsonSamplingMAB


def test_ab_detects_lift():
    res = ABTest.proportion_test(
        control_success=480, control_total=20000,
        treatment_success=600, treatment_total=20000,
        alpha=0.01,
    )
    assert res.relative_lift > 0
    assert res.significant is True
    assert res.p_value < 0.01


def test_ab_no_lift_not_significant():
    res = ABTest.proportion_test(500, 20000, 510, 20000, alpha=0.01)
    assert res.significant is False


def test_sample_size_positive():
    n = ABTest.required_sample_size(baseline_rate=0.025, mde=0.10)
    assert n > 0


def test_bh_correction_basic():
    p_values = [0.001, 0.008, 0.04, 0.5, 0.9]
    out = BenjaminiHochberg.correct(p_values, fdr=0.05)
    assert out[0] is True and out[-1] is False


def test_thompson_converges_to_best_arm():
    mab = ThompsonSamplingMAB()
    for arm in ["A", "B", "C"]:
        mab.add_arm(arm)
    # True CTRs
    truths = {"A": 0.02, "B": 0.05, "C": 0.03}
    import random
    random.seed(0)
    for _ in range(2000):
        chosen = mab.select_arm()
        reward = 1 if random.random() < truths[chosen] else 0
        mab.update(chosen, reward)
    snapshot = mab.snapshot()
    assert snapshot[0]["arm_id"] == "B"
