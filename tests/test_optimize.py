from maowise.optimize.engines import recommend_solutions


def test_recommend_basics():
    out = recommend_solutions(
        target={"alpha": 0.2, "epsilon": 0.8},
        current_hint=None,
        constraints={"voltage_V": [200, 500], "time_min": [5, 60]},
        n_solutions=3,
    )
    assert "solutions" in out and len(out["solutions"]) >= 1

