"""独立算例：金融舍入/硬约束/费率口径；能源假设缺失不能补零。"""

import copy
import json
from pathlib import Path

import pytest
from src.adapters.base import ProviderError
from src.tools.energy import calculate_energy
from src.tools.finance import calculate_finance

PRODUCT = json.loads(
    (Path(__file__).parents[2] / "src/fixtures/finance/products.json").read_text()
)["products"][0]


def test_zero_uses_fen_and_adjusts_last_payment():
    product = copy.deepcopy(PRODUCT)
    result = calculate_finance(
        32150000, product, {"down_payment_fen": 7990000, "terms_months": [60]}
    )
    plan = result["solutions"][0]
    assert plan["principal_fen"] == 24160000
    assert plan["monthly_payment_fen"] == 402667
    assert plan["last_payment_fen"] == 402647
    assert plan["total_installments_fen"] == 24160000
    assert plan["financing_cost_fen"] == 0
    assert product == PRODUCT


def test_rounding_cap_can_increase_down_payment_instead_of_false_no_solution():
    product = dict(PRODUCT, min_down_ratio=".3971", max_down_ratio=".8")
    result = calculate_finance(10000, product, {"terms_months": [60], "monthly_cap_fen": 101})
    assert result["state"] == "ready"
    plan = result["solutions"][0]
    assert plan["down_payment_fen"] == 3999
    assert plan["monthly_payment_fen"] == 100 and plan["last_payment_fen"] == 101


def test_no_solution_does_not_relax_cap_or_down():
    result = calculate_finance(
        32150000, PRODUCT, {"down_payment_max_fen": 7990000, "monthly_cap_fen": 350000}
    )
    assert result["state"] == "no_solution" and result["solutions"] == []


def test_equal_payment_known_monthly_rate_and_fee_no_double_count():
    p = dict(
        PRODUCT,
        method="equal_payment",
        monthly_interest_rate="0.01",
        terms_months=[12],
        min_down_ratio="0",
        financed_fees_fen=10000,
        upfront_fees_fen=5000,
    )
    plan = calculate_finance(1000000, p, {"down_payment_fen": 0})["solutions"][0]
    assert plan["monthly_payment_fen"] == 89737
    assert plan["financing_cost_fen"] == plan["total_installments_fen"] - 1010000 + 15000


def test_unknown_annual_fee_is_not_annual_interest():
    with pytest.raises(ProviderError, match="口径"):
        calculate_finance(10000, dict(PRODUCT, method="annual_fee", annual_fee_rate=0.03), {})
    with pytest.raises(ProviderError, match="缺失"):
        calculate_finance(10000, dict(PRODUCT, discount_fen=None), {})


def test_energy_independent_arithmetic_and_all_assumptions():
    values = dict(
        annual_km=20000,
        years=5,
        kwh_per_100km=15,
        electricity_yuan_per_kwh=1.5,
        liters_per_100km=10,
        fuel_yuan_per_liter=8,
        source="用户假设公共充电单价",
    )
    result = calculate_energy(values, 100)
    assert result["annual_electric_fen"] == 450000
    assert result["annual_fuel_fen"] == 1600000
    assert result["series"][-1]["saving_fen"] == 5750000
    with pytest.raises(ProviderError):
        calculate_energy(dict(values, electricity_yuan_per_kwh=None), 100)
    with pytest.raises(ProviderError):
        calculate_energy(dict(values, years=101), 100)
