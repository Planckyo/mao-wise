from maowise.models.infer_fwd import predict_performance


def test_predict_shape():
    out = predict_performance("MAO dc voltage 300 V time 10 min alpha 0.2 epsilon 0.8")
    assert set(["alpha", "epsilon", "confidence", "nearest_cases"]) <= set(out.keys())
    assert 0.0 <= out["alpha"] <= 1.0
    assert 0.0 <= out["epsilon"] <= 1.0

