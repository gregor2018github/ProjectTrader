# Merchant's Rise — Brainstorm

Fresh feature ideas, grounded in the current codebase. Tags: **Art** [None / Tint / Sprites×N] · **Effort** [S/M/L] · **Plugs into** [existing system]. `↪ extends` marks a sharpening of an existing TODO/reservoir note; everything else is new.

## 1. Quick Gains (high value, art-light, mostly UI/logic)

1. **Price percentile indicator.** On each good, show whether the current price is historically high/low as a 30-day percentile (color + ↑/↓ arrow, e.g. "near 90-day high"). Pure calc over `price_history_hourly/daily`. Turns the existing chart data into an at-a-glance buy/sell signal. *Art None · Effort S · Plugs into Good price history + market view.*

2. **Unrealized P&L on hover.** When hovering a good you own, show avg buy price (from FIFO `purchase_history`) and current unrealized profit/loss. The data is already tracked — just surface it. *Art None · Effort S · Plugs into Depot.purchase_history + tooltip.*

3. **Price alerts / watchlist.** Let the player set a target price per good; fire a `show_warning()` when crossed. Reuses the transient warning overlay. Very natural for a trading game. *Art None · Effort S–M · Plugs into warning system + hourly tick.*

4. **Net-worth glance panel.** A compact summary: cash, inventory value, outstanding debt, today's realized P&L. All values already exist in `Depot`; this is a layout, not new state. *Art None · Effort S · Plugs into Depot bookkeeping.*

5. **Event log / ledger.** ↪ extends (TODO "ledger system"). Concretely: `game_state.event_log: List[(datetime, category, text)]` appended at existing hooks (license signed, contract filled, big trade, crash, milestone). Scrollable modal reusing the standard `info_window` pattern. Closes the noted "no central event log" gap and unlocks alerts, milestones, and news to all write to one place. *Art None · Effort M · Plugs into all time/trade hooks + modal pattern.*

6. **"Best price in N days" markers in market view.** Tiny badge when a good is at its cheapest/most expensive in a window — encourages timing. Same calc as #1, different placement. *Art None · Effort S.*

7. **Keyboard hotkeys.** Pause/resume, cycle module on a side, jump to market/depot/map. Pure input routing in `keyboard_handler.py`. *Art None · Effort S.*

## 2. Economic Depth (make the market feel alive — all logic, no art)

8. **Market impact / slippage.** Large buy orders nudge price up, large sells nudge it down, scaled by order size vs `market_quantity`. **This finally gives the dormant `market_quantity` field meaning** without a full supply/demand rewrite. Makes big trades cost more and rewards splitting orders. *Art None · Effort S–M · Plugs into Depot.buy/sell + Good.*

9. **Bid-ask spread.** Buy slightly above mid, sell slightly below; spread widens for illiquid goods (low `market_quantity`) and during volatility. Adds a realistic friction and makes liquidity matter. Pairs naturally with #8. *Art None · Effort S–M · Plugs into Good price + trade pricing.*

10. **Seasonal price cycles.** A deterministic monthly modifier layered on the random walk, driven by `game_state.date`: wheat dips after autumn harvest, fish scarce in winter, wine peaks near festivals, wool dips after spring shearing. Gives each good a *personality* and a learnable rhythm to arbitrage. *Art None · Effort M · Plugs into Good.update_price + date.*

11. **Production-chain correlations.** Couple raw→refined goods with a lag: Wheat→Beer, Wool→Linen, Hide→leather goods, Stone→refined stone. A spike in the input propagates to the output a few days later. Turns 12 independent random walks into an interconnected economy. *Art None · Effort M · Plugs into Good.update_price (correlation matrix).*

12. **Rumor → shock pipeline (the free newspaper).** ↪ extends (reservoir "newspaper"). A lightweight always-on text headline ("Bandits on the eastern road — iron shipments delayed") that *foreshadows* a scheduled price shock days later, executed via the existing `apply_well_shock` mechanism. Gives an information edge as a free core feature, no literacy gate. Feeds the event log (#5). *Art None · Effort M · Plugs into well_shock + event log.*

13. **Festivals & market days.** Calendar events (monthly fair, harvest festival, saint's day) that temporarily lift trade volume and shift demand/prices. Pure date logic; optional single banner sprite. Gives the year a rhythm and predictable opportunity windows. *Art None or Sprites×1 · Effort M · Plugs into date + shock.*

14. **Traveling caravan / convoy event.** Periodically an NPC merchant "arrives" (dialogue + quick-trade) offering a bulk buy or sell of one random good at a premium/discount, limited quantity and time. Reuses dialogue + quick trade menu + an existing portrait. Event-driven liquidity and tension. *Art None (reuse portrait) · Effort M · Plugs into dialogue + quick_trade_menu.*

## 3. Goals & Progression (reasons to keep playing)

15. **Merchant rank / title ladder.** Peddler → Trader → Merchant → Patrician → Guildmaster, unlocked by lifetime wealth + trade volume (already tracked). Each rank grants concrete perks: lower transaction fees, larger loan ceiling, more base storage, guild access. Pure thresholds + perk flags; complements the faction-reputation idea rather than duplicating it. *Art None (or Sprites×N rank crests, optional) · Effort M · Plugs into Depot stats + constants.*

16. **Commissions (delivery contracts).** Distinct from trading *licenses*: a townsperson requests N units of a good by a deadline for a premium, via dialogue. Accept → obligation; fulfill → bonus (+ reputation); fail → penalty. Adds directed goals and a money source/sink. *Art None · Effort M · Plugs into dialogue + Depot.*

17. **Milestones / achievements.** Track and surface moments — first 1,000 gold, cornering a market, surviving a crash. Writes to and reads from the event log (#5). Cheap, satisfying, gives texture to progress. *Art None · Effort S–M · Plugs into event log.*

18. **Year-end review + taxes.** ↪ extends (reservoir "income/property tax"). At year roll-over, a summary modal of the year's P&L, best/worst goods (from `trade_cycles`), and a tax bill to pay. Reuses yearly time hook + bookkeeping. Provides closure and a recurring late-game money sink. *Art None · Effort M · Plugs into yearly tick + Depot history.*

## 4. World & Atmosphere (low-art flavor that supports the sim)

19. **Weather (tint + modifier only).** Daily weather state (clear/rain/storm/snow) shown as a light full-screen color tint plus a small icon, no animation. Storm → fish scarce; drought → wheat up; snow → slower movement. Ties atmosphere to the economy. *Art Tint + Sprites×~4 icons · Effort M · Plugs into daily tick + price modifier + map render.*

20. **Seasonal color grading.** Reuse the existing day/night tint system to shade the world by season (warm autumn, cool blue winter). Almost free given the lighting code already exists. *Art Tint · Effort S · Plugs into existing day/night lighting.*

21. **Town crier announcements.** Periodic text near the town hall surfacing the current rumor/festival/news. Reuses the message/dialogue overlay; no new art. Ties the rumor pipeline (#12) into the world visually. *Art None · Effort S · Plugs into message overlay.*

22. **Market hours visual state.** ↪ extends (TODO "trade only 6am–10pm" + "tarps at night"). Even without new sprites: grey/desaturate booths and disable quick-trade outside hours, with a tooltip. Reinforces the time-of-day loop using state you already compute. *Art None (Tint) · Effort S · Plugs into time + market view.*

## 5. Wild / Ambitious (go-big proposals)

23. **AI rival merchant(s).** One or more simple AI traders with their own cash who buy low / sell high in the same market and, via market impact (#8), actually move prices. Creates a living, competitive economy and someone to race on the rank ladder. Code-only — no sprites required (could surface as a name on a leaderboard). *Art None · Effort L · Plugs into Good pricing + market impact + rank.*

24. **Market cornering as emergent play.** With market impact (#8) + low `market_quantity` goods, buying up most of a good's supply lets you drive price then dump — but draws scrutiny (fine/reputation risk). Pure emergent consequence of #8 + reputation; a high-skill, high-risk strategy. *Art None · Effort M (on top of #8) · Plugs into market impact + reputation.*

25. **Hired help / apprentices (light management layer).** Hire NPCs (roster entries, no sprites): a *factor* who auto-buys a chosen good when it's cheap, a *clerk* who cuts transaction fees, a *watchman* who cuts theft risk. Each is a recurring wage vs. a concrete benefit. Adds an idle/optimization layer entirely in logic. *Art None · Effort M–L · Plugs into daily tick + Depot.*

26. **Economic disaster events.** Plague, blight, embargo: population drops (reuse `PopulationManager`), demand shifts, and tied goods spike (herbs/candles in a plague) via the shock mechanism. The dramatic cousin of festivals; feeds event log + news. *Art None · Effort M · Plugs into population + shock + event log.*

27. **Guild membership & dues.** Join a merchant guild for perks (cheaper licenses, exclusive goods, better loans) in exchange for dues and rules (price floors, obligations). A meaningful long-term faction choice that ties rank, reputation, and licenses together. *Art None or Sprites×1 building · Effort L · Plugs into licenses + reputation + rank.*

## Cross-cutting note

Many of these compose: **#5 event log** is the backbone for #12/#17/#18/#26; **#8 market impact** unlocks #9/#23/#24; **#10/#11/#13** make the economy worth studying instead of watching. A strong, low-art first wave would be: event log (#5) → market impact (#8) → seasonal cycles (#10) → price percentile & alerts (#1/#3) → commissions (#16). That sequence adds depth, signal, and goals with essentially zero animation.
