"""
Customer-concentration risk scorer (spec section 8) -- backlog basis only.

Core Release scope (spec section 21.1 / section 25 scope constraint): only
backlog concentration is implemented, since that's the basis the Symbotic
worked example (spec section 14) uses. Revenue, installed-base, and
projected-revenue concentration are Expansion Release (section 21.2).
`compute_concentration` deliberately rejects any other basis rather than
silently computing it, so callers can never mix concentration bases without
realizing it (spec section 8.5's core rule).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.schemas import ConcentrationBasis, CustomerConcentrationEntry

_BASIS_TO_FIELD: dict[str, str] = {
    "backlog": "contracted_backlog",
}


def customer_shares(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        raise ValueError("Total customer value must be positive to compute shares")
    return [v / total for v in values]


def hhi_decimal(shares: list[float]) -> float:
    """Spec 8.1: HHI_Decimal = sum(s_i^2)."""
    return sum(s**2 for s in shares)


def hhi_standard(shares: list[float]) -> float:
    """Spec 8.1: HHI_Standard = sum((100 x s_i)^2), i.e. the conventional 0-10,000 scale."""
    return sum((100.0 * s) ** 2 for s in shares)


def normalized_concentration_score(hhi_standard_value: float) -> float:
    """Spec 8.2: a 0-100 display of the standard HHI, not an alternative methodology."""
    return hhi_standard_value / 100.0


def effective_customer_count(shares: list[float]) -> float:
    """Spec 8.3: N_Effective = 1 / sum(s_i^2)."""
    decimal_hhi = hhi_decimal(shares)
    if decimal_hhi <= 0:
        raise ValueError("HHI must be positive to compute effective customer count")
    return 1.0 / decimal_hhi


def largest_customer_share(shares: list[float]) -> float:
    return max(shares)


def top_n_share(shares: list[float], n: int = 3) -> float:
    return sum(sorted(shares, reverse=True)[:n])


@dataclass
class ConcentrationResult:
    basis: str
    num_customers: int
    largest_customer_share: float
    top_three_share: float
    hhi_standard: float
    normalized_concentration_score: float
    effective_customer_count: float


def compute_concentration(entries: list[CustomerConcentrationEntry], basis: ConcentrationBasis = "backlog") -> ConcentrationResult:
    if basis not in _BASIS_TO_FIELD:
        raise ValueError(
            f"Concentration basis '{basis}' is not supported in Core Release (spec section 21.1/25). "
            f"Only {list(_BASIS_TO_FIELD)} is available; revenue/installed-base/projected-revenue bases "
            "are Expansion Release (section 21.2)."
        )
    field_name = _BASIS_TO_FIELD[basis]
    values = [getattr(entry, field_name) for entry in entries]
    shares = customer_shares(values)
    standard = hhi_standard(shares)

    return ConcentrationResult(
        basis=basis,
        num_customers=len(entries),
        largest_customer_share=largest_customer_share(shares),
        top_three_share=top_n_share(shares, 3),
        hhi_standard=standard,
        normalized_concentration_score=normalized_concentration_score(standard),
        effective_customer_count=effective_customer_count(shares),
    )


@dataclass
class DiversificationTargetResult:
    new_accounts_required: int
    projected_hhi_standard: float
    achieved: bool


def solve_diversification_target(
    current_values: list[float],
    target_hhi_standard: float,
    new_account_value: float,
    max_new_accounts: int = 100_000,
) -> DiversificationTargetResult:
    """Spec 8.6: smallest integer n of equal-sized new accounts (value =
    `new_account_value` each) such that HHI(n) <= target_hhi_standard.

    HHI(n) = sum((R_i / (R + nA))^2) + n * (A / (R + nA))^2, reported on the
    standard 0-10,000 scale to match `target_hhi_standard`.
    """
    total_current = sum(current_values)

    last_hhi_standard = None
    for n in range(0, max_new_accounts + 1):
        denominator = total_current + n * new_account_value
        if denominator <= 0:
            continue
        existing_term = sum((r / denominator) ** 2 for r in current_values)
        new_term = n * (new_account_value / denominator) ** 2
        hhi_dec = existing_term + new_term
        last_hhi_standard = hhi_dec * 10_000
        if last_hhi_standard <= target_hhi_standard:
            return DiversificationTargetResult(new_accounts_required=n, projected_hhi_standard=last_hhi_standard, achieved=True)

    return DiversificationTargetResult(new_accounts_required=max_new_accounts, projected_hhi_standard=last_hhi_standard or 0.0, achieved=False)
