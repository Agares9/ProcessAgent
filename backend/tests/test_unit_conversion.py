from app.harness.task_executor import _normalize_unit


def test_common_manufacturing_units():
    assert _normalize_unit(3, "万元") == 30000
    assert _normalize_unit(2, "MWh") == 2000
    assert _normalize_unit(1.5, "吨") == 1500
    assert _normalize_unit(2, "MW") == 2000
    assert _normalize_unit(15, "%") == 0.15
