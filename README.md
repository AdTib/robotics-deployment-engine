# Robotics Deployment Economics Engine


Live app: https://robotics-deployment-engine.streamlit.app


A decision engine for deployment-stage robotics and autonomous-systems companies. It answers one question: given your commercial pipeline, deployment capacity, unit economics, and customer portfolio, when do you actually become sustainable, and how fast can you cut customer-concentration risk?

## What's built right now

This is Core Release scope only (spec §21.1, restated in the scope constraint at the top of §25). Here's the actual state:

- **One commercial-model preset: RaaS.** Direct-sale and hybrid aren't built.
- **Deterministic scenarios only.** No Monte Carlo.
- **One concentration basis: backlog.** Revenue, installed-base, and projected-revenue concentration aren't built.
- **97 engine tests, all passing.**
- **A working Streamlit app**, built on top of the tested engine.

`engine/monte_carlo.py` doesn't exist. That's Expansion Release, not this.

Run it with `streamlit run app.py` (details below). Seven pages: Inputs (five tabs: Business Model, Commercial Funnel, Deployment Funnel, Deployment Capacity, Customer Portfolio), Funnel View, Capacity View, Fleet Economics View, Concentration View, Scenario Simulator, and Worked Examples. Every number on screen comes from calling an `engine.*` function directly. The app layer doesn't compute anything itself. It just wires widgets, tracks session state, and draws charts.

## The entity hierarchy

An Account contains one or more Sites. A Site might start as a Pilot and later expand into a full production deployment. Units move through real states: Contracted (signed, not built yet), Installed (physically on-site), Commissioned/Operational (actually earning revenue), Steady-State (running at expected utilization). The model never assumes one account equals one deployment, and it never assumes a signed contract means revenue starts tomorrow (spec §22, rules 1-3).

## How the modules connect

```
engine/funnel.py       Account-level commercial funnel, 10 default stages.
                       Triangular(min, mode, max) dwell times. Outputs a
                       monthly "newly contracted units" series per cohort.
        |
        v
engine/deployment.py   Unit-level pre-capacity stages: committed, scheduled,
                       in production/procurement, delivered. Turns the
                       contracted-units series into "Commercially Ready
                       Units." Not capacity-constrained yet; that's next.
        |
        v
engine/capacity.py     Gates ready units against manufacturing, deployment-
                       team, and commissioning capacity:
                       Units Deployed_t = min(Ready_t + Backlog_(t-1),
                                              Manufacturing_t, Implementation_t,
                                              Commissioning_t)
                       Tracks backlog and the revenue that backlog defers.
                       Capacity expansions carry a lead time and a ramp.
        |
        v
engine/economics.py    RaaS unit and company economics. Revenue and cost
                       scale with a utilization ramp. Upfront costs and
                       customer payments hit cash flow the month a unit is
                       actually deployed, never earlier (spec §22 rule 11).
        |
        v
engine/concentration.py  Backlog HHI, a normalized 0-100 score, effective
                       customer count, largest/top-3 share, and a
                       diversification-target solver.
        |
        v
engine/simulation.py   Runs all of the above together for one scenario, and
                       holds the deterministic scenario transforms: slow/fast
                       conversion, anchor vs. diversified accounts, capacity-
                       constrained vs. expansion, utilization/service-cost
                       downside. Plus a comparison-table helper.
```

`engine/schemas.py` (Pydantic models) and `engine/validation.py` (cross-field checks) sit underneath all of it.

## Why there are three breakeven numbers, not one

**Operating Breakeven Fleet Size** (`economics.operating_breakeven_fleet_size`) asks: at steady state, what fleet size makes annual contribution margin cover annual fixed costs? It says nothing about timing. It's a target, not a forecast.

**Unit Deployment Payback** (`economics.unit_payback_months_constant` / `unit_payback_months_with_ramp`) asks: how long does one deployed unit take to earn back its own upfront cost? It doesn't care about the rest of the company.

**Company Cash Breakeven Month** (`economics.company_cash_breakeven_month`) asks: when does the whole company's cumulative cash flow turn non-negative? This is the only one of the three that accounts for deployment timing and ramp-up.

A company can clear its operating breakeven fleet size and still be burning cash, because it hasn't deployed enough units yet. These numbers get reported separately because collapsing them into one "breakeven" is the most common way this kind of model goes wrong.

`economics.minimum_cash_balance` and `economics.external_capital_required` are a different pair again. They fold in your opening cash balance and answer a financing question: how much capital do you need so you never go negative?

## Backlog concentration, not revenue or installed-base

Core Release computes backlog concentration only. `engine.concentration.compute_concentration` raises a `ValueError`, naming Expansion Release by name, if you ask for any other basis. That's on purpose. It stops someone from accidentally computing "concentration" without knowing which concentration they got. The Symbotic worked example (`data/symbotic_demo_customers.csv`) is a backlog case, not a recognized-revenue case.

## Source classification

Every external number in `/data` is labeled:

- **disclosed**: a company, regulator, or credible source said this directly, with a URL in `source_registry.csv`
- **derived**: calculated from disclosed information
- **assumed**: a modeling input where the real value is unknown
- **scenario**: deliberately varied to compare outcomes

Full audit trail is in `data/source_registry.csv`. Two entries need a flag: `BOTAUTO-003` and `BOTAUTO-004`, the "30 trucks by 2026" and "breakeven at 100 trucks by 2027" figures from spec §13. I searched for a primary source on those two numbers and couldn't find one. They're marked `assumed` with `confidence: low`. They still get used, as the anchor for the fixed-cost sensitivity matrix, but never as a reconstruction of Bot Auto's actual finances.

One more thing worth flagging: Bedrock Robotics builds autonomous excavators for construction. Not trucks. The spec's problem statement (§1.4) mentions it in a paragraph that's otherwise about trucking, but that's a segment mismatch. `data/calibration_timelines.csv` files it under `construction`, not `autonomous_trucking`, with a note explaining why, so it doesn't get blended into trucking dwell-time defaults.

## Limitations

- RaaS only. No direct-sale or hybrid economics.
- Backlog concentration only.
- Deterministic only. Dwell-time ranges use the closed-form mean and variance of a triangular distribution, plus a normal approximation for percentile ranges. Nothing in this codebase samples randomly.
- Revenue and variable support cost share the same utilization-ramp curve (see the `engine/economics.py` module docstring for why). If your contracts split a flat base fee from usage-based revenue, this will understate early revenue and overstate early cost by roughly the same amount. Call the lower-level functions directly with separate ramps if that distinction matters to you.
- Contracts don't renew. A unit drops out of the active fleet after `contract_term_months`.
- No CSV or Excel export yet.
- The Inputs page only rebuilds its downstream session state (`unit_economics`, `existing_customers`, etc.) when its own tab actually renders. Streamlit only runs the code for whatever page you're currently on. After loading a Worked Examples preset, visit the matching Inputs tab once before checking an output view. The app tells you this in its success message, right when you need it.

## Using your own company's data

1. Build your own `CompanyAssumptions`, `UnitEconomics`, `FunnelStage` lists, `CapacityEntry` lists, and `CustomerConcentrationEntry` lists with the Pydantic schemas in `engine/schemas.py`. Any `tests/test_*.py` file shows how to construct them.
2. Run them through `engine.validation` first: `validate_funnel_stages`, `validate_company_assumptions`, `validate_unit_economics`, `validate_capacity_entries`, `validate_customer_concentration_entries`. Fix whatever it flags.
3. Build an `engine.simulation.ScenarioAssumptions` and call `run_scenario(...)`.
4. Use the `make_*_scenario` builders in `engine/simulation.py` for the comparison scenarios in spec §9.2, then `compare_scenarios([...])` for a summary table.
5. Don't reuse `data/*_demo_inputs.csv` or `data/*_demo_customers.csv` as real inputs. They're worked examples with labeled disclosed/assumed/scenario values, not a template for real unit economics.

## Running the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

All 97 should pass. Test files map one-to-one to spec §16's required list: `test_validation.py`, `test_funnel.py`, `test_deployment.py`, `test_capacity.py`, `test_economics.py`, `test_concentration.py`, and `test_simulation.py` for integration tests.

## Running the app

```bash
source .venv/bin/activate
streamlit run app.py
```

Open the URL it prints (default `http://localhost:8501`). Start on the Inputs page. Defaults are already filled in, so every other page works right away. The "Input status" checklist at the bottom of the Inputs page shows what's currently valid.
