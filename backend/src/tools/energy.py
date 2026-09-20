"""仅比较能源费用，不将保险、折旧等未计算项目称为总持有成本。"""

from src.adapters.base import ProviderError
from src.tools.finance import decimal, fen


def calculate_energy(data: dict, max_years: int) -> dict:
    required = (
        "annual_km",
        "years",
        "kwh_per_100km",
        "electricity_yuan_per_kwh",
        "liters_per_100km",
        "fuel_yuan_per_liter",
        "source",
    )
    if any(data.get(key) is None for key in required) or not data.get("source"):
        raise ProviderError("ENERGY_INPUT_MISSING", "能源估算需要全部假设及来源，不足时不绘图")
    values = {key: decimal(data[key]) for key in required[:-1]}
    if any(value <= 0 for value in values.values()) or values["years"] != int(values["years"]):
        raise ProviderError("ENERGY_INPUT_INVALID", "能源参数须为正数，持有年数须为整数")
    # 避免恶意模型参数产生无界列表；输出只按用户明确的有限周期生成。
    if values["years"] > max_years:
        raise ProviderError("ENERGY_INPUT_INVALID", "持有周期超出估算支持范围")
    electric = values["annual_km"] * values["kwh_per_100km"] * values["electricity_yuan_per_kwh"]
    fuel = values["annual_km"] * values["liters_per_100km"] * values["fuel_yuan_per_liter"]
    return {
        "assumptions": data,
        "annual_electric_fen": fen(electric),
        "annual_fuel_fen": fen(fuel),
        "series": [
            {
                "year": year,
                "electric_fen": fen(electric * year),
                "fuel_fen": fen(fuel * year),
                "saving_fen": fen((fuel - electric) * year),
            }
            for year in range(1, int(values["years"]) + 1)
        ],
        "scope": "仅能源成本，不含购车、保险、维修、折旧",
        "label": "Estimate",
    }
