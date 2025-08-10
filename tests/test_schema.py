from maowise.utils.schema import validate_record


def test_validate_required_and_ranges():
    rec = {
        "substrate_alloy": "Al6061",
        "electrolyte_family": "silicate",
        "electrolyte_components": [],
        "mode": "dc",
        "voltage_V": 300,
        "current_density_A_dm2": 10,
        "frequency_Hz": 1000,
        "duty_cycle_pct": 30,
        "time_min": 20,
        "alpha_150_2600": 1.2,
        "epsilon_3000_30000": -0.2,
        "source_pdf": "a.pdf",
        "page": 1,
        "sample_id": "sid",
        "extraction_status": "ok",
    }
    out = validate_record(rec)
    assert 0.0 <= out["alpha_150_2600"] <= 1.0
    assert 0.0 <= out["epsilon_3000_30000"] <= 1.0

