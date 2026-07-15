"""
Required concentration tests (spec section 16.4). Core Release scope is
backlog concentration only (spec section 21.1/25) -- revenue and
installed-base bases are Expansion Release and are tested here only to the
extent of confirming they are rejected, not silently computed.
"""

import pytest

from engine.concentration import (
    ConcentrationResult,
    compute_concentration,
    customer_shares,
    effective_customer_count,
    hhi_standard,
    solve_diversification_target,
)
from engine.schemas import CustomerConcentrationEntry


def entry(customer_id, backlog):
    return CustomerConcentrationEntry(customer_id=customer_id, customer_name=customer_id, contracted_backlog=backlog)


class TestHHIBenchmarks:
    """Required tests: one customer -> 10,000; two equal -> 5,000; ten equal -> 1,000."""

    def test_one_customer_hhi_10000(self):
        result = compute_concentration([entry("A", 1_000_000)])
        assert result.hhi_standard == pytest.approx(10_000)
        assert result.largest_customer_share == pytest.approx(1.0)
        assert result.normalized_concentration_score == pytest.approx(100.0)

    def test_two_equal_customers_hhi_5000(self):
        result = compute_concentration([entry("A", 500), entry("B", 500)])
        assert result.hhi_standard == pytest.approx(5_000)
        assert result.largest_customer_share == pytest.approx(0.5)

    def test_ten_equal_customers_hhi_1000(self):
        entries = [entry(f"C{i}", 100) for i in range(10)]
        result = compute_concentration(entries)
        assert result.hhi_standard == pytest.approx(1_000)


class TestEffectiveCustomerCount:
    """Required test: effective-customer-count calculation."""

    def test_equal_customers_effective_count_equals_actual_count(self):
        shares = customer_shares([100, 100, 100, 100])
        assert effective_customer_count(shares) == pytest.approx(4.0)

    def test_concentrated_customers_effective_count_is_lower_than_actual(self):
        # One dominant customer (90%) and 9 tiny ones splitting the rest.
        values = [900] + [100 / 9] * 9
        shares = customer_shares(values)
        n_eff = effective_customer_count(shares)
        assert n_eff < 10
        assert n_eff == pytest.approx(1.0 / hhi_standard(shares) * 10_000, rel=1e-6)

    def test_via_compute_concentration(self):
        result = compute_concentration([entry("A", 500), entry("B", 500)])
        assert result.effective_customer_count == pytest.approx(2.0)


class TestConcentrationResultShape:
    def test_result_is_labeled_with_basis(self):
        result = compute_concentration([entry("A", 100), entry("B", 200), entry("C", 700)])
        assert isinstance(result, ConcentrationResult)
        assert result.basis == "backlog"
        assert result.num_customers == 3
        # top_three_share should be 100% since there are only 3 customers
        assert result.top_three_share == pytest.approx(1.0)


class TestDiversificationTarget:
    """Required test: diversification target with equal-sized new accounts."""

    def test_hand_calculated_three_new_accounts(self):
        # Single existing customer with backlog 1000 (HHI = 10,000).
        # Adding equal-sized new accounts of value 1000 each:
        # n=1: shares = [1000/2000, 1000/2000] -> HHI = 0.25+0.25=0.5 -> 5000
        # n=2: shares = [1000/3000]*3 -> HHI = 3*(1/3)^2 = 1/3 -> 3333.33
        # n=3: shares = [1000/4000]*4 -> HHI = 4*(0.25)^2 = 0.25 -> 2500
        result = solve_diversification_target(current_values=[1000], target_hhi_standard=3000, new_account_value=1000)
        assert result.achieved is True
        assert result.new_accounts_required == 3
        assert result.projected_hhi_standard == pytest.approx(2500.0)

    def test_zero_new_accounts_needed_if_already_below_target(self):
        result = solve_diversification_target(current_values=[100, 100, 100], target_hhi_standard=5000, new_account_value=100)
        assert result.new_accounts_required == 0
        assert result.achieved is True

    def test_unreachable_target_within_cap_reports_not_achieved(self):
        result = solve_diversification_target(
            current_values=[1000], target_hhi_standard=0.001, new_account_value=1000, max_new_accounts=2
        )
        assert result.achieved is False
        assert result.new_accounts_required == 2


class TestBasisSeparation:
    """Required test: revenue and backlog concentration treated separately.

    Core Release supports backlog only; requesting any other basis must be
    rejected explicitly rather than silently computed on the wrong field.
    """

    def test_backlog_basis_succeeds(self):
        result = compute_concentration([entry("A", 100), entry("B", 200)], basis="backlog")
        assert result.basis == "backlog"

    def test_unsupported_basis_raises(self):
        with pytest.raises(ValueError, match="Expansion Release"):
            compute_concentration([entry("A", 100)], basis="revenue")  # type: ignore[arg-type]
