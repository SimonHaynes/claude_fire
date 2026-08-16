---
name: uk-annuities
description: UK lifetime annuities — what they pay at a given age, how joint life, guarantees, escalation and enhanced underwriting change the rate, why rates move with gilt yields, and when annuitising beats drawdown. Use for any question about buying an annuity, how much guaranteed income a pot buys, or securing a spending floor.
---

# UK lifetime annuities

Owns annuity pricing and the annuitise-or-drawdown decision.
`uk-pension-tax-strategy` owns the tax on the income (it is pension income, taxed
as such). `legal-and-trust-structuring` owns the immediate needs annuity, which
is a different product bought at the point of entering care.

**Price with the model; never quote a rate from memory.** Rates moved 82% between
2020 and 2026 on the same age and premium. Any figure recalled rather than
computed is wrong by more than every option choice combined.

    .venv/bin/python tools/annuity_quote.py --premium 200000 --age 65
    .venv/bin/python tools/annuity_quote.py --age 65 --compare
    .venv/bin/python tools/annuity_quote.py --age 65 --history

`Scenario.income_annuity` prices through the same model, at the annuitant's age
in the year they buy — so a scenario that annuitises later gets the better rate,
and the projection carries the **real** income. `define-scenarios` owns how to
set one up; everything about *which* shape to buy is here.

## What sets the rate

Two things, and only one of them is about the client:

| | |
|---|---|
| **The gilt curve** | Insurers back annuities with gilts and long corporate bonds. Rates follow a gilt selloff within weeks |
| **Mortality** | Annuitants outlive the population — the unhealthy do not buy annuities — and mortality keeps improving |

`retireplan.annuity` prices from the Bank of England curve
(`tools/fetch_gilt_yields.py`) and ONS mortality, calibrated to published
best-buy tables. Every option adjustment is computed from the same annuity
factor rather than assumed, so the relationships hold even as the level moves.

**Most of what a client thinks is "their" annuity rate is the month they
bought.** `--history` shows it: £100,000 at 65 bought £8,645 a year in January
2000, £4,741 in July 2020 and £7,855 in August 2026. Rates today are near their
best in two decades — which is the single most decision-relevant fact in this
skill, and it has nothing to do with the client.

## The options, and what each costs

Indicative at 65, August 2026 — **recompute, do not quote these**:

| Option | Effect on income | Why |
|---|---|---|
| Single life, level, no guarantee | the headline rate | the benchmark everything else is quoted against |
| 5-year guarantee | −0.5% | cheap: dying inside five years is unlikely at 65 |
| 10-year guarantee | −2% | and far dearer at 85, where it insures a real risk |
| Joint life 50% | −7% | spouse three years younger is the market convention |
| Joint life 100% | −13% | |
| 3% fixed escalation | −27% | takes ~14 years to draw level |
| RPI-linked | −30% | dearer than 3% fixed: index-linked gilts trade rich |
| Enhanced (smoker) | +7% | |
| Enhanced (serious impairment) | +20-30% | only an underwriter can price this |

**Age is worth more than any of them.** 65 → 75 is roughly +27% on the same
premium, because the money is spread over fewer expected years.

## The thing clients are not told

A level annuity is **nominally** flat, which means it falls in real terms every
year of the contract. At 3% inflation it halves in purchasing power in 23 years
— well inside a 65-year-old's life expectancy of about 24 years.

    year 0   £15,711        year 20  £8,699
    year 10  £11,690        year 30  £6,473        (£200,000 at 65, 3% inflation)

Yet **level still usually wins on total real income to life expectancy**, because
the 27% haircut on an escalating annuity is a lot to make back. `--compare`
prints both columns. The honest framing:

- **Level** buys more money sooner and protects against dying early.
- **Escalating or RPI-linked** buys less now and protects against living long and
  inflation running hot — which are the two risks an annuity is *for*.

State which risk the client is buying insurance against. A client who wants a
guaranteed floor and takes a level annuity has bought a floor that sinks.

## When an annuity earns its place

**The case for.** It is the only product that pays until you die however long
that is. Nothing else removes longevity risk, and a floor of guaranteed income
under essential spending is what lets the rest of a portfolio take real risk —
the "floor and upside" argument. It also removes sequence risk on the annuitised
part entirely, and needs no decisions ever again, which matters more than
clients expect at 85.

**The case against.** The capital is gone: nothing passes to the estate beyond
any guarantee period, and after April 2027 that is a smaller disadvantage than it
was, since an unspent pension now bears IHT too. It cannot be reversed, cannot be
increased, and locks in the gilt curve on one day.

**Annuitise partially, and later, unless there is a reason not to.** Rates rise
with age, so deferring buys a higher rate — but deferring also means paying for
that income from the portfolio in the meantime. Model both rather than asserting
either.

**Check enhanced underwriting every time.** A quarter of buyers qualify for an
enhancement and most never ask. It is free money for a client with a diagnosis, a
smoking history, high blood pressure or a raised BMI, and it is the largest
single uplift available on this list after age itself.

## The traps

- **Quoting a rate from memory.** It is a market price, not a constant.
- **Selling a level annuity as "a guaranteed income for life"** without saying
  the guarantee is nominal.
- **Ignoring the spouse.** A single-life annuity on a married client leaves the
  survivor with nothing. Ask before quoting.
- **Ignoring the open market option.** The client's own provider is rarely best;
  the spread between best and worst is around 16% on the same day.
- **Treating the income as tax-free.** It is pension income, taxed at the
  client's marginal rate — see `uk-pension-tax-strategy`.
- **Comparing an annuity rate with a portfolio return.** An annuity rate includes
  return *of* capital; a 7.9% annuity is not a 7.9% yield.
- **Assuming the MPAA is triggered.** Buying a lifetime annuity does not trigger
  it; taking income drawdown does.

## How to advise with this

- **Price it, then show the real income path.** The rate alone is not advice.
- **Frame the choice as which risk is being insured** — dying early, living long,
  or inflation. The options map onto those three and nothing else.
- **Say what today's rate owes to the market** rather than to the client, using
  `--history`. A client buying near a two-decade high should be told so.
- **Quantify, then refer.** Only a whole-of-market broker's underwritten quote is
  real; the model's error is smaller than the spread between providers, but it is
  still an estimate.

A planning estimate, not a quote, and not regulated financial advice. Annuity
purchase is irreversible — every case belongs in front of an FCA-regulated
adviser before anyone acts.
