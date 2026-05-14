from src.rtb_engine.auction import FirstPriceAuction, SecondPriceAuction


def test_second_price_clears_at_second_plus_epsilon():
    auc = SecondPriceAuction(epsilon=0.01)
    res = auc.run({"a": 5.0, "b": 3.5, "c": 2.0}, floor=1.0)
    assert res.winner_id == "a"
    # clearing should be max(second=3.5, floor=1.0) + epsilon = 3.51
    assert res.clearing_price == 3.51


def test_second_price_caps_at_top_bid():
    auc = SecondPriceAuction(epsilon=0.5)
    res = auc.run({"a": 1.0, "b": 0.9}, floor=0.0)
    assert res.winner_id == "a"
    assert res.clearing_price <= 1.0


def test_floor_rejects_low_bids():
    auc = SecondPriceAuction()
    res = auc.run({"a": 0.5}, floor=1.0)
    assert res.winner_id is None and res.clearing_price == 0.0


def test_first_price():
    auc = FirstPriceAuction()
    res = auc.run({"a": 2.0, "b": 1.0})
    assert res.winner_id == "a" and res.clearing_price == 2.0
