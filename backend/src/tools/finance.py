"""金额一律为分。Decimal 计算，最后一期吸收舍入差，不修改捕获快照。"""

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

from src.adapters.base import ProviderError


def decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError()
        return result
    except Exception:
        raise ProviderError("INVALID_NUMBER", "计算输入须为有限数字") from None


def fen(value: Decimal, rounding=ROUND_HALF_UP) -> int:
    return int(value.quantize(Decimal("1"), rounding=rounding))


def calculate_finance(price_fen: int, product: dict, constraints: dict) -> dict:
    """产品必须明确费率计息口径、费用及优惠，未知项不能按零补齐。"""
    required = {
        "id",
        "method",
        "terms_months",
        "financed_fees_fen",
        "upfront_fees_fen",
        "discount_fen",
        "min_down_ratio",
        "max_down_ratio",
        "source_kind",
    }
    if not required <= product.keys() or any(product[k] is None for k in required):
        raise ProviderError("FINANCE_RULES_MISSING", "费用、优惠或产品规则缺失，无法可靠试算")
    if price_fen <= 0:
        raise ProviderError("AMOUNT_CONFLICT", "车辆价格必须大于零")
    method = product["method"]
    if method == "zero_interest":
        rate = Decimal(0)
    elif method == "equal_payment" and product.get("monthly_interest_rate") is not None:
        rate = decimal(product["monthly_interest_rate"])
        if rate <= 0:
            raise ProviderError("RATE_BASIS_UNKNOWN", "月利率必须明确且大于零")
    else:
        raise ProviderError(
            "RATE_BASIS_UNKNOWN", "未知计息口径或不支持的产品，不能将年化费率当利率"
        )
    fees, upfront, discount = (
        decimal(product[k]) for k in ("financed_fees_fen", "upfront_fees_fen", "discount_fen")
    )
    if min(fees, upfront, discount) < 0 or discount >= price_fen:
        raise ProviderError("AMOUNT_CONFLICT", "费用或优惠与车价冲突")
    net = Decimal(price_fen) + fees - discount
    lower = max(
        fen(Decimal(price_fen) * decimal(product["min_down_ratio"]), ROUND_CEILING),
        int(constraints.get("down_payment_min_fen") or 0),
    )
    upper = min(
        fen(Decimal(price_fen) * decimal(product["max_down_ratio"]), ROUND_FLOOR),
        int(constraints["down_payment_max_fen"])
        if constraints.get("down_payment_max_fen") is not None
        else fen(net),
        fen(net),
    )
    cap = constraints.get("monthly_cap_fen")
    if cap is not None and cap <= 0:
        raise ProviderError("INVALID_CONSTRAINT", "月供上限必须大于零")
    terms = constraints.get("terms_months") or product["terms_months"]
    solutions = []
    for n in sorted(set(terms) & set(product["terms_months"])):
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            raise ProviderError("INVALID_TERM", "期限必须为正整数月")
        factor = Decimal(1) / n if rate == 0 else rate * (1 + rate) ** n / ((1 + rate) ** n - 1)
        minimum = max(lower, fen(net - Decimal(cap) / factor, ROUND_CEILING) if cap else lower)
        explicit = constraints.get("down_payment_fen")
        downs = range(minimum, min(upper, minimum + n) + 1) if explicit is None else [int(explicit)]
        for down in sorted(downs):
            if down < minimum or down > upper:
                continue
            principal = net - down
            monthly = fen(principal * factor)
            balance = principal
            for _ in range(n - 1):
                balance = balance * (1 + rate) - monthly
            last = fen(balance * (1 + rate))
            # 约束检查覆盖末期金额，不用舍入后的低值掩盖超预算。
            if last < 0 or (cap and max(monthly, last) > cap):
                continue
            total = monthly * (n - 1) + last
            solutions.append(
                {
                    "product_id": product["id"],
                    "term_months": n,
                    "down_payment_fen": down,
                    "principal_fen": fen(principal),
                    "monthly_payment_fen": monthly,
                    "last_payment_fen": last,
                    "total_installments_fen": total,
                    "financing_cost_fen": total - fen(principal) + fen(fees + upfront),
                    "upfront_fees_fen": fen(upfront),
                    "financed_fees_fen": fen(fees),
                    "method": method,
                    "source_kind": product["source_kind"],
                }
            )
            break
    solutions.sort(
        key=lambda x: (x["financing_cost_fen"], x["down_payment_fen"], x["monthly_payment_fen"])
    )
    return {
        "state": "ready" if solutions else "no_solution",
        "solutions": solutions,
        "unmet_constraints": [] if solutions else ["所选期限、首付范围和月供上限无法同时满足"],
        "constraints": constraints,
        "price_fen": price_fen,
        "note": "确定性试算，不代表金融审批；Mock 产品不是当前官方金融方案",
    }
