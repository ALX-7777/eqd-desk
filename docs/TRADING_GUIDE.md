# How to Trade Well — an EQD Market-Maker's Guide

You have built **EQD Greeks Lab** — a simulator of an equity-derivatives index market-maker on the S&P 500. This guide is the trader's manual that goes with it: it teaches you how to *think* like the desk you're simulating, from what your job actually is, through the greeks, volatility, structures, market-making, hedging, P&L attribution, and the psychology that keeps you in your seat. It is written for a student prepping for an EQD trading internship, and it assumes you want intuition you can defend in an interview, not formulas you've memorised.

## How to use this guide

Read it once, end to end, to build the mental model. Then **practise every idea in the app** — each section points you at the tab that drills it. Reading teaches you the words; the simulator teaches you the reflexes. The closing "Putting it together" section gives you a daily routine and a feature-by-feature map of which tab trains which skill. Don't try to internalise it all at once: take one idea, drill it until it's automatic, then move to the next.

## Foundations: what "trading well" actually means

### Your real job: warehouse risk, get paid for it

Forget the movies. A market-maker is not a fortune-teller betting on whether the S&P goes up tomorrow. Your job is to be the person who is **always willing to trade** — to quote a price on both sides, buy or sell, whenever a client asks. In exchange for providing that service (liquidity), you get paid a small toll on every trade. You are a toll booth, not a gambler.

When a client buys an option from you, you're now **short** that option. You didn't choose that position because you have a view — you took it because the client wanted it and you got paid to take it. The risk that lands on your book is a **by-product** of doing business, not the point of it. The point is the toll.

This reframes everything. A directional trader asks "where is the market going?" A market-maker asks "what risk am I now holding, and how do I get paid more than it costs me to hold it?" In the **Trading Simulator** tab, notice you never get to pick the trade — the RFQ (request-for-quote: a client asking you to price something) comes to you. All you control is the **price** and what you do with the risk afterward.

### The daily loop

Every trading day is the same loop, and the whole app is built around it:

- **Client asks.** An RFQ lands — a single option or a structure, a side, a size.
- **You quote two-way.** You show a **bid** (where you'll buy) and an **ask** (where you'll sell) around your estimate of fair value. The gap between them is your **spread**.
- **You win or lose the trade.** If your price is competitive you get filled; if you're too greedy a competitor wins it. Fill logic compares your quote to a simulated fair value plus noise.
- **You're left with risk.** Now you hold greeks you didn't ask for — delta, gamma, vega, the lot.
- **You hedge.** Trade the future to flatten delta; trade other options to knock down gamma or vega — paying **transaction costs** each time. The **Desk Advisor** suggests concrete hedges (instrument, side, size, why).
- **At end-of-day, you attribute P&L.** The **P&L explain** decomposes your day into delta/gamma/theta/vega/vanna/volga plus a residual, so you know *why* you made or lost money, not just *that* you did.

Run that loop a few hundred times and you're a trader. Run it badly a few hundred times and you're unemployed.

### Where edge actually comes from

**Edge** is your structural, repeatable advantage — the reason you make money *on average* over many trades. For a market-maker it comes from two places, and **neither is prediction**:

- **The bid/ask spread.** You buy at 9.90, sell at 10.10, fair value is 10.00. Every round trip earns you 0.20 regardless of direction. Quote on 50 trades a day capturing a few cents of edge each and it compounds.
- **Skew / the lean.** You don't have to quote symmetrically. If you're already long too much vega, you shade (lean) your prices to *encourage* clients to take vega *off* you and *discourage* trades that pile more on. In the simulator, the **lean** control is exactly this: tilt your quote to attract the flow you want and repel the flow you don't.

Notice what's missing: a forecast. You make money from the **structure** of how you quote and manage risk, not from being right about tomorrow's close. A good market-maker with no view will reliably beat a brilliant forecaster who quotes lazily.

### Expected value vs outcome

Internalize this or nothing else will stick: **a good trade can lose money, and a bad trade can make money.** You captured 20 cents of edge, hedged properly, and the market gapped against your residual risk overnight — you lost on the day but you *traded well*. Conversely, you quoted a reckless price, forgot to hedge, and got bailed out by luck — you made money but you *traded badly*.

Judge yourself on **expected value (EV)** — the average outcome if this exact decision played out a thousand times — not on the single result you happened to get. One coin flip tells you nothing about whether the coin is fair. Your edge only shows up over **many** trades, so any single day's P&L is mostly noise around it.

### Risk, reward, survival, and why process beats P&L

The catch: those many trades only happen **if you're still here**. The fastest way to destroy a positive-EV business is to size so big that one bad tail wipes you out before the average has time to work. So real trading well is **edge × time**, and time requires survival:

- **Cap your risk.** Watch net gamma and vega in the book; an unhedged tail can dwarf a week of toll-collecting. Use the P&L explain to see which greek would hurt you in a shock.
- **Respect asymmetry.** Being short gamma and short vega into a selloff (the leverage effect: **spot down → vol up**) stacks losses — exactly what the simulator's correlated path is built to teach.
- **Trust the process.** Tighten spreads, lean correctly, hedge cheaply, size sanely. Do that and the P&L takes care of itself across the sample. Chase the P&L directly and you'll abandon your edge the first time variance bites.

Grade your **decisions**, not your daily number. That's the whole game.

## The greeks: your risk language

Greeks are the vocabulary you trade in. A client doesn't ask "are you long or short?" — your **net greeks** answer that for you, and they tell you exactly what move will hurt. Learn to read them the way a pilot reads a cockpit: one glance, full situational awareness. Every number below is a sensitivity — "if X moves one unit, my P&L moves this much." Build each in the **Greeks Lab** and drag the inputs until the signs and sizes are second nature.

### The first-order greeks: your directional and time exposures

- **Delta (Δ)** — sensitivity of option value to **spot**, the dollar P&L per 1-point move in the index. A call's delta runs 0→+1, a put's −1→0. It's also your *hedge ratio*: long 0.5 delta on an SPX option means you sell 0.5 future to be flat. Delta costs you nothing directly — it's the risk you're *supposed* to hedge away as a market-maker. You don't get paid to be long the market; you get paid for the greeks below.
- **Vega (ν)** — sensitivity to **implied volatility**, reported per 1 vol-point (16% → 17%). Long options = long vega; you profit if the market re-prices vol higher. A 1-year ATM SPX option might carry ~20 vega: VIX up a point, you make $20 per contract-unit. Vega is the price of your **view on implied vol**.
- **Theta (Θ)** — **time decay**, P&L per calendar day, holding everything else fixed. Long options bleed theta (negative); short options earn it. This is the *rent* you pay to hold gamma — and it's the other side of the most important trade in the book (below).
- **Rho (ρ)** — sensitivity to **rates**, per 1%. Smallest of the bunch for short-dated index trades; it matters for long-dated structures and is mostly a financing afterthought on a daily desk. Don't obsess over it early.

### The cross-greeks: where the real money and pain live

- **Gamma (Γ)** — the *curvature*: how fast your delta changes as spot moves. Long gamma means your delta moves *in your favour* — you get longer as the market rallies, shorter as it sells off, so re-hedging locks in profit. Gamma is huge for **short-dated ATM** options and collapses for long-dated ones. It's the engine of "gamma scalping."
- **Vanna (∂Δ/∂σ = ∂ν/∂S)** — how your **delta moves when vol moves**, equivalently how your **vega moves when spot moves**. Critical because of skew: as spot falls and vol rises, vanna reshapes your delta whether you like it or not.
- **Volga / vomma (∂ν/∂σ)** — convexity of vega: how your **vega changes as vol changes**. Long volga (e.g. long wings) means you get *longer vega as vol spikes* — you want this in a crisis. It's the "vol-of-vol" greek.

### The relationship every trader must own: gamma ↔ theta

These two are **locked together by the Black–Scholes PDE** — you cannot have one without paying for the other. For a delta-hedged book, the daily P&L is approximately:

**P&L ≈ ½ · Γ · S² · (realised_vol² − implied_vol²) · dt**

Read this slowly, because it *is* the job. When you're **long gamma**, you re-hedge constantly — sell highs, buy lows — and you capture the *realised* variance of the path. You paid for that privilege in theta, which is priced off *implied* vol. So:

- Realised > implied → your scalping out-earns your decay → **you win**.
- Realised < implied → quiet market, theta bleed dominates → **you lose**.

Buying an option is **buying realised vol and selling implied** — gamma and theta are just the two faces of that bet. In the Trading Simulator, watch your P&L explain: the gamma line and theta line should roughly net to this formula each tick. That's your sanity check. (The next section puts concrete numbers on the scalping side of this trade.)

### Gamma vs vega across maturities

Same "long vol" instinct splits by tenor, and conflating them is a classic interview trap:

- **Short-dated options = a gamma / realised-vol play.** Big gamma, big theta, tiny vega. You live or die on the *path* — how much the market actually moves day to day.
- **Long-dated options = a vega / implied-vol play.** Big vega, negligible gamma. You barely scalp; you're betting the *level* of implied vol re-rates. A 2-year option is a vol-level position, not a path bet.

Want to express "vol is cheap, market will be choppy *this week*"? Buy front-month gamma. "VIX term structure is too low for the next year"? Buy back-month vega. Different greeks, different trades.

### The leverage effect — why vanna and volga bite

Equity index vol isn't static: **spot down → vol up** (the leverage / skew effect). This correlation is *why* the cross-greeks matter. If spot and vol were independent, vanna and volga would be cosmetic. But on an index, a selloff *simultaneously* moves spot and lifts the whole surface — so vanna converts that vol spike into a delta you didn't expect, and volga converts it into extra vega exactly when vol is exploding. Short the wings and a crash hits you three ways at once: gamma, vanna, *and* volga. This is why downside skew is expensive and why your simulator's leverage-effect path makes hedging feel real instead of theoretical.

### Reading your net book as one line

Aggregate every position into net greeks and you have a single-sentence risk summary:

> *"Long $2M delta, short gamma, long 50k vega, paying 30k theta/day, short vanna."*

That instantly says: I lose if the market moves hard either way (short gamma), I profit if vol re-rates up (long vega), I'm bleeding rent daily, and I'm exposed to the spot–vol correlation (short vanna). Before you quote any RFQ, ask what it does to that line — and let the Desk Advisor's hedge suggestions teach you which instrument flattens the greek that's screaming loudest.

## Trading volatility

An options market-maker is, at heart, a **volatility trader**. Spot direction is something you hedge away; what you keep — what you actually get paid or punished for — is your view on how much the market will *move*. Get this section into your bones and the rest of the desk falls into place.

### The central bet: implied vs realised

Every option price embeds an **implied volatility (IV)** — the market's forecast of future movement, the number you back out of the price via Black–Scholes. **Realised volatility (RV)** is what actually happens: the annualised standard deviation of the underlying's returns over the life of the trade.

You met the master equation in the last section — `½·Γ·S²·(RV² − IV²)·dt` per day for a delta-hedged book. Trading vol means forming a view on whether IV is too high or too low versus what will actually print, then positioning so your **gamma** has the right sign: own gamma when you think the market will move more than IV implies, sell it when you think it'll move less. The Greeks Lab makes the ½·Γ·S² term concrete; the Simulator's P&L explain shows it accumulating tick by tick.

### The vol surface has three knobs

IV is not one number — it's a **surface** over strike and maturity. Three features, three separate trades:

- **ATM level** — the overall height, gauged by **VIX** (30-day at-the-money SPX vol, in vol points: VIX 18 → σ ≈ 0.18). This is your headline "is vol cheap or rich" dial.
- **Skew** — IV plotted against strike slopes *down*: low strikes (puts) trade at higher IV than high strikes (calls). On SPX this is steep and permanent. **Why:** indices crash down, not up — the leverage effect means realised vol spikes precisely when puts pay off, plus there's structural demand for crash protection from people who are long the market. Index puts are *rich* for a reason; selling them naked is selling insurance into a fire. Your Simulator models this — the surface shifts up when spot drops — so vanna and volga actually bite.
- **Term structure** — IV across maturities. Usually upward-sloping ("contango") in calm markets, **inverting** in a panic when near-dated vol explodes above long-dated. A steep front-end inversion is a classic stress tell.

### Gamma scalping in practice

This is how you *harvest* realised vol. Buy an option, **delta-hedge** it continuously by trading the underlying. Because you're long gamma, every move leaves you with a delta in the profitable direction: spot rises, you're now long delta, you sell the future into strength; spot falls, you're short delta, you buy weakness. **You mechanically buy low and sell high**, and each round-trip banks cash proportional to the *square* of the move.

The catch: you pay **theta** for the privilege — long gamma always bleeds time value. So gamma scalping is a race. If realised vol over the day exceeds the IV you paid, your scalping gains beat your theta bill and you profit. If the tape goes dead, theta grinds you down.

**Worked feel:** long a 1-week ATM straddle at 16 vol. Your daily breakeven move is roughly σ/√252 ≈ 16%/15.9 ≈ **1.0% of spot**. Realise 1.5% daily swings → you win. Realise 0.4% → theta eats you. **Short gamma is the exact mirror:** you collect theta and pray for stillness, and you get steamrolled when it moves. That asymmetry — bounded income, ugly tail — is why short-gamma blowups are a genre.

### When to be long vs short vol

- **Long vol** when IV looks low versus likely RV: pre-catalyst (earnings cluster, Fed, election), when VIX is in the low-mid teens and complacent, or when you expect a regime break.
- **Short vol** when IV is fat versus realisable RV: post-event "vol crush," elevated VIX with no fresh catalyst, harvesting the persistent **variance risk premium** (IV averages ~1–2 points above subsequent RV — sellers get paid for warehousing crash risk). Just respect the tail.

### Vega, vol-of-vol, and the wings

- **Vega** scales with √T, which is why **long-dated options are your vega plays** and short-dated are your gamma/realised plays — same engine, different end of the curve.
- **Volga (vomma)** is your **vol-of-vol** exposure, and it's largest in the **wings** (out-of-the-money strikes), near-zero ATM. Long volga = long convexity in vol: you profit when IV itself becomes volatile. Owning wings is how you get long vol-of-vol.
- **Vanna** links skew and spot — it's why a skewed book's delta drifts as vol moves, and the Desk Advisor will flag it when it's large.

### The variance swap and the VIX gauge

A **variance swap** pays the difference between realised *variance* and a fixed strike — pure vol exposure with no path-dependent delta hedging needed. Its fair strike is built by **replicating with a 1/K² strip of options across all strikes** (more weight on low strikes — that's the Exotics tab's intuition). **VIX is essentially the square root of that fair variance** on SPX.

This matters because variance/VIX prices the *whole surface*, so it sits **above** ATM implied — the extra is the **skew and convexity premium** (those rich OTM puts in the strip lift fair variance). VIX > ATM IV is normal and quantifies how much the wings are bid.

### Reading cheap vs rich

- **Rich:** VIX well above trailing RV (large variance premium), steep skew, inverted term structure, a recent spike still elevated. Lean toward selling — carefully.
- **Cheap:** VIX near or below RV, flat skew, complacent contango ahead of a known catalyst. Lean toward owning gamma. Use the Simulator's real-history replay to drill spotting these regimes blind, before you risk a quote.

## Strategies & structures: expressing a view cleanly

A structure is just a bundle of vanilla legs. The art is choosing legs so the **net greek signature** matches your view and *nothing else does*. A clean trade has the greek you want loud and every other greek quiet — that way, if you're right, you get paid for being right, not for getting lucky on a greek you didn't mean to be holding. Build each of these in the **Strategy Builder** and read the aggregate greeks; if a greek you didn't intend is large, your trade is dirty.

### Vertical spread — defined-risk directional
Buy one option, sell another of the same type and expiry, different strike (e.g. buy the 5000 call, sell the 5100 call). **View:** moderate directional move, with a known max profit/loss. **Greek signature:** net delta in your direction, but gamma, vega and theta are *small* because the long and short legs largely cancel — that's the point. **When to use:** you have a directional lean but want to cap cost and risk, or you want delta without paying for a big vega bill. **Principal risk:** it's a spread, so your upside is capped; you can be right on direction and still leave money on the table. Cheap, boring, and the workhorse of directional expression.

### Straddle / strangle — long or short vol, big-move bet
Straddle: buy (or sell) a call and a put at the **same** strike. Strangle: same but out-of-the-money strikes (cheaper, needs a bigger move). **View:** pure magnitude — you think the realised move will be **larger** (long) or **smaller** (short) than what implied vol is pricing. **Greek signature:** near-zero delta at inception, big **gamma** and big **vega**, and (if long) large negative **theta** — you bleed time value every day the market sits still. **When to use:** long into an event you think is underpriced; short to harvest premium when you think the market will be quiet. **Principal risk:** long straddles are a race between gamma profits and theta bleed; short straddles have *unlimited* loss and brutal negative gamma in a fast move — the classic "picking up pennies in front of a steamroller."

### Risk reversal — the pure skew bet (big vanna)
Sell a downside put, buy an upside call (or vice versa), usually for near-zero cost. **View:** you have a view on **skew** — the fact that downside puts trade at higher implied vol than upside calls. **Greek signature:** long delta, near-zero vega *at the money*, and crucially large **vanna** (∂delta/∂vol). When spot falls and vol rises (the leverage effect), your delta moves against you sharply. **When to use:** to express that downside skew is too steep or too cheap, or as a cheap leveraged directional play. **Principal risk:** vanna and tail risk — you're short the downside put, so a crash hits you twice (spot and the vol spike). In the **Trading Simulator**, watch a risk reversal's delta swing as the surface shifts; that's vanna biting.

### Butterfly — pin / vol-of-vol
Buy one low strike, sell two middle strikes, buy one high strike (all same expiry). **View:** the market will **pin** near the middle strike at expiry, or more abstractly, that the wings (vol-of-vol) are overpriced. **Greek signature:** cheap, defined risk, peak payoff at the centre; net vega is small and changes sign around the body. **When to use:** high-conviction pin bets near expiry, or to sell expensive convexity in the tails. **Principal risk:** narrow profit zone — you need the market to land in a tight band, and the position is mostly worthless otherwise.

### Iron condor — range-bound, sell vol / income
Sell an out-of-the-money put spread and an out-of-the-money call spread. **View:** the market stays **inside a range**; you collect premium. **Greek signature:** short vega, short gamma, **positive theta** (your income engine), with defined risk thanks to the long wings. **When to use:** quiet, range-bound regimes when you want to harvest theta with capped tail risk. **Principal risk:** a sharp move to either wing; you're short gamma, so losses accelerate exactly when you're wrong. Income strategies feel free until they aren't.

### Calendar spread — term-structure bet
Sell a near-dated option, buy a longer-dated one at the same strike. **View:** the **term structure** of vol — you want near-dated implied to be rich relative to far-dated, and/or expect the front to decay faster. **Greek signature:** **positive vega** (the long leg dominates), positive theta near the strike (short front bleeds faster), and sensitivity to the *shape* of the curve, not just its level. **When to use:** front-month implied looks expensive vs back; you want long vega with the near-term theta partly funded. **Principal risk:** a big spot move away from the strike kills both legs, and a parallel collapse in vol hurts your net-long-vega book.

### Isolating one greek
The general recipe: **add legs whose unwanted greeks offset while the target greek adds.** Want vega with no delta? Use an at-the-money straddle (deltas cancel, vegas add). Want a vol-of-vol/skew bet with no net vega? Use a butterfly or risk reversal so the body's vega nets out but the *curvature/asymmetry* sensitivity remains. Want gamma without a vega bill? Go short-dated, where gamma dwarfs vega. Want term-structure exposure with no level exposure? A calendar nets the vega *level* down and leaves the *slope*. Build it in the **Strategy Builder**, read every aggregate greek, and if a greek you didn't ask for is loud, re-strike or re-weight until it's quiet. Clean structures are how you get paid for your actual view.

## Making markets: pricing, quoting & capturing edge

You are not an investor here. You're a **market-maker**: you quote prices on demand, take the other side of whatever the client wants, and earn a living off the **spread** and your skill at managing the risk you're left holding. Investing is about being right on direction. Market-making is about being right on *price* and disciplined on *risk*. Different game entirely.

### The RFQ → quote → fill loop

An RFQ is a client asking: *"Where are you on the SPX Dec 5000 put?"* They don't tell you if they want to buy or sell — that's the whole point of a **two-way quote**. You show a **bid** (where you'll buy) and an **ask/offer** (where you'll sell), and the client picks. In the Trading Simulator, RFQs hit your queue; you respond with bid/ask, and fill logic decides whether you win it.

Your quote is built from two pieces:

- **Fair value** — your model mid. The Greeks Lab BSM price at *your* marked vol. This is your honest estimate of what the thing is worth.
- **Spread** — fair value ± a margin you choose. Quote `fair − s` / `fair + s`. That `s` (per side) is your edge.

If fair value is 42.00 and you show 41.50 / 42.50, your spread is 1.00 wide, 0.50 per side. Win a buy at 41.50, the option's "worth" 42.00, you've booked **0.50 of theoretical edge** — *before* hedging costs and before the market moves against you.

### The spread/fill tradeoff

Here's the central tension every market-maker lives with:

- **Wider spread** → more edge *per trade*, but you win *less flow*. Clients shop around; the tightest price wins. Quote too wide and you just watch trades go to competitors.
- **Tighter spread** → more flow, more turnover, but thin margins and less cushion when you're wrong.

There's no universal answer — it depends on **liquidity and your risk appetite**. Heuristics: a liquid front-month ATM SPX option might trade on a vol spread of ~0.25–0.5 vol points; an illiquid long-dated wing or a chunky structure, several points. **Size scales the spread** — a 50,000-vega ticket deserves a wider quote than 500 vega, because you'll wear the risk longer and hedge it at more cost.

### Adverse selection — the reason you can't just quote tight

**Adverse selection** is the brutal truth that the client knows something you don't, *on average*. The flow that lifts your offer tends to be flow that's about to be right. If you quote a razor-thin market, you win exactly the trades you'd rather have lost. Your spread isn't greed — it's **compensation for trading against better-informed counterparties** and for the cost of unwinding risk you didn't want. When a sharp client repeatedly hits one side, *that itself is information*: widen, or move your mid.

### Skewing / leaning — quote to fix your book, not in a vacuum

This is where pros separate from amateurs. Your quote shouldn't sit symmetrically around fair value — **lean it** toward the trade that *reduces your existing inventory risk*.

Say you're already **long 20,000 vega** (you bought a lot of options and you're desperate not to buy more). On the next vol RFQ, **lean your quote lower**: maybe 41.30 / 42.30 instead of 41.50 / 42.50. You've made your *offer* more attractive (you want to sell vega) and your *bid* less attractive (you don't want to buy more). You're paying clients, via price, to hedge you. The Simulator's **lean** control does exactly this; the **Desk Advisor** tells you which way your net greeks point so you know which side to favor.

The intuition: **inventory is a cost.** Long gamma bleeds theta; long vega is exposed to a vol crush; a big delta is naked directional risk. A market-maker who leans well gets flow to *flatten* their book for free, instead of paying transaction costs to hedge in the future.

### Quoting a structure as one net package

When a client RFQs a **risk reversal** or **call spread**, do not quote each leg separately and sum — quote the **net package**. Why:

- The legs **partially offset**. A 1×1 call spread has far less vega and gamma than the long leg alone, so it deserves a *much* tighter spread than two independent quotes.
- You hedge the *residual* risk of the whole structure, not each leg, so price the residual.
- Quoting legwise double-counts your spread and makes you uncompetitive on exactly the structures that are cheap for you to warehouse.

Use the Strategy Builder to see the **aggregate greeks** of the package, then set one spread sized to *that* net risk.

### Price the risk you'll warehouse, not just the value

The deepest discipline: when you win a trade, you don't get the value — you get the **leftover risk**, and you hold it until you can hedge or unwind. So price two things:

1. The **theoretical edge** (fair value vs. your quote).
2. The **cost to carry and hedge** what you're left with — bid/ask in the hedge, gamma bleed, vega exposure overnight, vanna/volga you can't cleanly offset.

A trade with 0.50 of edge that hands you 30,000 of unhedgeable wing vega is a *worse* trade than 0.20 of edge on something you can flatten in the future for one tick. **Edge is what's left after the risk is paid for.** Quote that number, not the model mid.

## Hedging & risk management: the right tool for each greek

The single most important skill on a market-making desk isn't pricing — it's **risk management**: taking the risk a client dumps on you and reshaping it into something you can sleep on. The core idea is simple: **each greek has a "natural" hedging instrument that gives you a lot of that greek and little of anything else.** Use the wrong tool and you create three new problems while fixing one. Let's go greek by greek, then talk about how hedges collide.

### Match the greek to the instrument

- **Delta → the future (or index forward).** Delta is your sensitivity to spot. The future is a **delta-one** instrument: one point of spot = one point of P&L, full stop. No gamma, no vega, no theta. It's the cleanest, cheapest, most liquid hedge you have. **Always hedge delta with the future** unless you have a specific reason not to. In the Trading Simulator, after any fill your first instinct should be to flatten delta in the future — it's the move with zero side effects.
- **Vega → ATM options.** At-the-money options carry the most vega per lot, and vega grows with maturity (√T). If you're short 40,000 vega from selling a client a strangle, you buy it back most efficiently with longer-dated ATM straddles. Buying far OTM wings to cover vega is inefficient: you'd need a huge number of lots, dragging in skew and gamma you didn't want.
- **Gamma → SHORT-dated ATM options.** Gamma is **densest in short-dated at-the-money options** — a one-week ATM option has enormous gamma and tiny vega; a two-year ATM option is the reverse. So if you're short gamma and getting whipsawed (re-hedging delta at bad prices every time spot moves), you cover it with **front-month ATM** options, not LEAPS. This is the gamma/vega split the Greeks Lab makes visual: shrink T and watch ATM gamma spike while vega collapses.

### Hedges interact — clean up after yourself

Here's the trap beginners fall into. **Options are bundles of greeks.** When you buy ATM options to cover vega, you also just bought a pile of **gamma** and some **delta**. The hedge isn't done when vega is flat — you've moved your other risks.

The discipline is **hedge in order of "purity," then re-clean delta last**:

1. Fix the messy, option-only greeks first (vega, then gamma) using options.
2. Each options trade dumps delta on you — **so re-flatten delta in the future as the final step.** The future is free of side effects, so it's always the last thing you touch.

Concrete example: you're short 30,000 vega and short gamma. You buy 6-month ATM straddles to cover vega — now you're vega-flat but you've added back some gamma (good, you wanted that) and you're long 150 deltas from the residual. You sell 150 futures, and you're clean. **Two trades, in the right order.** Do delta first and you'd just have to redo it.

### Transaction costs: hedging isn't free

Every hedge crosses a bid-ask spread (and the simulator charges you for it). That changes the calculus in two ways:

- **Prioritise the biggest, cheapest-to-fix risk.** Delta first — it's the cheapest cross (futures are tight) and usually your largest dollar risk. A messy delta will hurt you faster than a small vanna imbalance.
- **Don't over-trim small greeks.** If you're carrying 200 vega on a book that routinely runs 30,000, leave it. Chasing every tiny greek to zero just **bleeds you on spreads** — the cure costs more than the disease. Set a threshold ("I don't react to vanna under X") and hold to it. The Desk Advisor flags the risks worth acting on; ignore the noise.

### Sizing, limits, concentration, pin risk

- **Position sizing & risk limits.** Real desks run hard limits: max net vega, max gamma, max delta. Treat your simulator book the same — pick a vega limit and refuse to let a single juicy RFQ blow through it, however good the edge looks. **Edge means nothing if the position can take you to a loss you can't survive.**
- **Concentration.** Net greeks lie. Being "vega-flat" while long a ton of 1-week vega and short a ton of 2-year vega is **not flat** — it's a term-structure bet that nets to zero today and bites tomorrow. Watch the *distribution* of risk across strikes and maturities, not just the totals.
- **Pin risk near expiry.** As an option approaches expiry **at-the-money**, gamma explodes and delta flips violently between 0 and 1 on tiny spot moves. You can be delta-flat at the close and wake up grossly long or short after settlement. **Reduce ATM size before expiry** rather than trying to hedge the un-hedgeable.

### Order of operations on a messy book

When your book is a mess after a busy session, work from **slowest-to-fix to fastest-to-fix**:

1. **Vega** (term structure / level) — the hardest to source, fix it with ATM options while liquidity is there.
2. **Gamma** — front-month ATM options for the convexity you need.
3. **Delta** — flatten in the future, **last**, because every step above just changed it.

Same logic every time: leave the frictionless instrument for the end, and the residual cleans up in one trade.

## Reading your P&L: attribution & the daily process

You made money today. Good — but **why**? If you can't decompose it, you got lucky, and lucky doesn't survive a bad week. The single most important habit a vol trader builds is the **P&L explain**: tearing the day's profit into the pieces of risk that produced it. Your Trading Simulator already does this for you in the live P&L explain panel. Learn to read it the way a doctor reads a chart.

### The Taylor expansion is your explain

A vol book's value depends on a few inputs: spot `S`, vol `σ`, and time `t`. When those move over a day, the change in your book's value is well-approximated by a **second-order Taylor expansion** — the same greeks you studied in the Greeks Lab, now used as *coefficients on the actual moves*:

```
ΔP&L ≈ Δ·dS                       (delta — directional)
     + ½·Γ·dS²                    (gamma — convexity in spot)
     + Θ·dt                       (theta — time decay, the rent)
     + Vega·dσ                    (vega — level of vol)
     + Vanna·dS·dσ                (cross: how delta drifts as vol moves)
     + ½·Volga·dσ²                (convexity in vol)
     + residual
```

Each term is a number you can compute: take the greek you *started* the day with, multiply by the move that *actually happened*. Example: you're long gamma and spot moves 30 points — the gamma term is ½·Γ·(30)², scaled to your contract size, a concrete dollar figure. Do this for every term and sum them.

### What a clean explain tells you

A **clean explain** is one where the sum of the greek terms ≈ your actual day's P&L, and the **residual** (actual minus explained) is small — say under 5-10% of the gross move. That tells you three things:

- Your **risk is measured**. The positions you think you hold are the positions you actually hold.
- Your **model is behaving**. The greeks you're quoting from are the greeks that materialised.
- You **understand your day**. "I made $40k: $50k of gamma scalping, minus $15k theta, plus $5k vega as VIX ticked up." That sentence is the job.

A clean explain also *teaches you which bet paid*. If you're long gamma and the gamma term is your big winner, the market realised more vol than you paid for — your thesis was right.

### When the residual screams

The **residual** is the most informative number on the page. A big residual is never noise to ignore — it's a flag:

- **A gap / large move.** Taylor is a *local* approximation. On a 4% down day, ½·Γ·dS² misses the higher-order convexity (that's **speed**, ∂Γ/∂S) and the explain leaks into residual. Big moves break the quadratic — expected, but note it.
- **A model issue.** If the residual is chronically large on *quiet* days, your surface is moving in a way your greeks don't capture — e.g. skew steepening you're not pricing, or your leverage effect (spot-vol correlation) misfiring. Add **vanna** to the explain before blaming the model; unexplained vanna is the classic culprit on an equity index book.
- **Risk you're not measuring.** Term-structure shifts, dividend moves, rate moves — if your explain has no bucket for it, it dumps into residual. The residual is your map of *blind spots*.

Heuristic: residual under ~10% on a normal day is healthy. Persistently above that, hunt for the missing greek.

### Realised-vs-implied: the scorecard

The master equation from the greeks section — `½·Γ·S²·(σ_realised² − σ_implied²)` per day — *is* your scorecard once a book is delta-hedged. You **bought** vol at implied (say VIX = 16%); the market **delivered** realised vol (the actual size of daily moves). In the simulator, compare the day's realised move against the implied you paid — that difference, scaled by your gamma, *is* your gamma P&L line in the explain. A vol trader's edge is forecasting that gap.

### Turning the explain into improvement

The explain isn't bookkeeping — it's a **feedback loop**. Every day, ask: *Did the bet I intended make the money?* If you're long vega for a vol spike and your P&L came entirely from gamma scalping, you were right by accident. Log your residuals; a drifting residual means your model is decaying. Over weeks, the explain teaches you which risks you read well and which blindside you — and that, more than any single winning trade, is what makes a market-maker.

## Discipline, psychology & the mistakes that blow people up

Pricing is the easy part. The hard part is sitting in a seat for eight hours, getting punched by the market, and still making the *next* decision cleanly. Most people who wash out of a trading seat don't do so because their Black-Scholes was wrong. They blow up because their behaviour was wrong. This section is the part of the job no formula teaches you.

### The behavioural edge: process over outcome

Your edge as a market-maker is **structural** — you get paid the bid-ask spread for providing liquidity, and over thousands of trades that edge compounds *if* you don't sabotage it. That means:

- **Judge decisions by process, not P&L.** A trade can be right and lose money (you quoted a fair price, the market gapped). A trade can be wrong and make money (you left a fat unhedged delta and got lucky). The market pays out randomly in the short run; only your process is in your control. After every fill in the **Trading Simulator**, ask "given what I knew, was the quote and the hedge correct?" — not "did it print green?"
- **Cut losers fast, let the book run.** A losing position is information: your view was wrong or the risk grew past your limit. Hesitation is where small losses become career losses. Define the exit *before* you're in pain.
- **Don't chase.** If you miss a level, it's gone. Re-entering worse to "make it back" is how a 2-point miss becomes a 10-point loss.
- **Size for survival.** Risk so that the *worst plausible day* — not the average day — leaves you trading tomorrow. A common desk heuristic: no single position should be able to lose more than a small fraction (say 1-2%) of your risk budget on a 1-sigma move. If a 1% spot move blows through your daily stop, you're too big, full stop.
- **No revenge trades.** After a loss, your job is to make the *same* disciplined decision you'd make cold. Doubling size to "get it back" is the single most reliable way to turn a bad day into a blow-up.
- **Respect the tail.** The leverage effect is real: spot down, vol up, the whole surface shifts, and your short-gamma, short-vega positions hurt *together*, not independently. The simulator's GBM-with-leverage and real-history replay exist precisely so you feel a 1987 or 2020-style gap. Position so one of those doesn't end you.

### The classic mistakes — and the tell for each

- **Over-hedging.** Re-hedging delta on every tiny tick *bleeds the spread* — every future trade costs you transaction costs and crossing the bid-ask. If you're short gamma you must re-hedge, but do it in **bands** (e.g. re-hedge when delta drifts past ±X, not continuously). Watch the cost line in the simulator's P&L explain: if your theta is being eaten by hedging costs, you're churning.
- **Leaving delta unhedged.** The opposite sin. An unhedged delta means you're no longer a market-maker — you're punting direction, which is *not* your edge. After every fill, neutralise delta to your band. The Desk Advisor will tell you instrument, side, and size; learn to pre-empt it.
- **Confusing luck with skill.** You left a delta on, spot moved your way, you made money. That's a **bad decision with a good outcome** — and if you bank the lesson "leaving delta on works," you'll repeat it until it kills you. Log *why* each green day was green.
- **Short gamma into a moving market.** Short gamma means your delta moves *against* you as spot moves — you sell as it falls, buy as it rises, locking in losses while you scramble to hedge. Fine if realised vol stays below the implied you sold; lethal if the market starts trending. Know your gamma sign at all times.
- **Ignoring skew and vanna.** Equity skew isn't decoration. When spot drops, vol rises, and **vanna** means your delta shifts *even before spot fully moves*. Traders who hedge spot but ignore vanna get repeatedly wrong-footed in selloffs. Watch the vanna term in the P&L explain — when it's large, your "delta-neutral" book isn't.
- **Over-sizing.** Underlies all of the above. A position too big forces panic hedging, prevents you cutting cleanly, and turns a normal move into an existential one.

### Habits of consistently good traders

They keep positions small enough to think clearly. They write down their reasoning so outcome can't rewrite memory. They flatten risk they don't understand rather than hoping. They treat limits as hard walls, not suggestions. And they're *boring* — consistency beats heroics over a career.

### Drills to build the reflexes

- **The hedge-band drill.** Run a trending replay slice short gamma. First pass: re-hedge every tick and watch costs bleed. Second pass: use ±X delta bands. Compare net P&L — feel the trade-off directly.
- **The decision journal.** For ten RFQs, write your intended quote, lean, and hedge *before* you see the result. Tally process-correct vs P&L-positive. Internalise that they're different.
- **The tail drill.** Take a max short-gamma, short-vega book into the worst real-history slice you can find. Note where your stop *should* have fired. Size down until you'd survive it.
- **The vanna hunt.** Build a risk reversal, flatten spot delta, then move vol in the sim and watch your delta reappear. That's vanna — hedge it deliberately, not by accident.

## Putting it together

You now have the whole loop. The skill is making it routine — the same disciplined steps every day, regardless of yesterday's P&L.

### The daily routine

1. **Read the regime.** Before any RFQ, glance at the tape: where's VIX vs trailing realised, is skew steep or flat, is the term structure in contango or inverted? That tells you whether to lean toward owning or selling vol.
2. **Read your book as one line.** Net delta, gamma, vega, theta, vanna. Know in one sentence what move hurts you most.
3. **Quote every RFQ off fair value + a spread, leaned to flatten your book.** Size the spread to the net risk of the package and to liquidity; widen against adverse selection and size.
4. **Hedge in order, slowest-to-fix first.** Vega and gamma with options, then flatten delta in the future *last* — and only act on greeks above your threshold, minding transaction costs.
5. **Respect your limits.** Hard walls on net vega, gamma, delta. No single juicy RFQ breaches them. Reduce ATM size into expiry to dodge pin risk.
6. **At end-of-day, mark honestly and run the P&L explain.** Reconcile the greek terms to actual P&L, interrogate the residual, and ask whether the bet you *intended* is the one that paid.
7. **Grade the decision, not the number.** Log why the day was what it was. Plan tomorrow's realised-vs-implied view.

### Practise in the simulator

| Skill to build | Where to drill it |
|---|---|
| Greek signs, sizes, and how each moves with spot/vol/time | **Greeks Lab** — drag S, σ, T; watch ATM gamma spike as T shrinks and vega grow as T rises |
| The gamma↔theta / realised-vs-implied trade | **Greeks Lab** for the ½·Γ·S² intuition, then **Trading Simulator** P&L explain to watch it accrue |
| Expressing a view with a clean greek signature | **Strategy Builder** — build verticals, straddles, risk reversals, butterflies, condors, calendars; read aggregate greeks until only the greek you want is loud |
| Skew, vanna, and the leverage effect | **Strategy Builder** (risk reversal) + **Trading Simulator** (watch delta drift as the surface shifts) |
| Vol-of-vol, variance, the 1/K² strip and VIX intuition | **Exotics** — variance swap and the wings; digitals and barriers for pin/path risk |
| Two-way quoting, spread/fill tradeoff, leaning to fix inventory | **Trading Simulator** — quote RFQs, tune spread and lean, win/lose against fill logic |
| Hedging the right greek with the right instrument, in the right order | **Trading Simulator** + **Desk Advisor** — flatten delta in the future, reshape gamma/vega with options, mind transaction costs |
| Reading a P&L explain and chasing the residual | **Trading Simulator** P&L explain — reconcile terms, hunt the missing greek |
| Process-over-outcome discipline, hedge bands, tail survival | **Trading Simulator** real-history replay — the hedge-band, decision-journal, tail, and vanna drills |

Master the loop here, in a seat where mistakes cost nothing, and you'll walk into the interview — and the desk — already fluent in the only thing that matters: not predicting the market, but pricing it, warehousing its risk, and getting paid for both.
