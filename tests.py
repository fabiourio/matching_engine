from decimal import Decimal
from engine import MatchingEngine
from models import EventType, Side, PegSide

D = Decimal
passed = 0
failed = 0

def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {label}")

def events_of_type(events, t):
    return [e for e in events if e.event_type == t]

def fresh():
    return MatchingEngine()


# ── 1. Limit rests when no counterparty ──
e = fresh()
ev = e.submit_limit(Side.BUY, D("100"), 10)
check("1 - limit rests alone", len(events_of_type(ev, EventType.ORDER_CREATED)) == 1)
check("1 - no trades", len(events_of_type(ev, EventType.TRADE)) == 0)

# ── 2. Two limits that don't cross ──
e = fresh()
e.submit_limit(Side.BUY, D("99"), 10)
ev = e.submit_limit(Side.SELL, D("101"), 10)
check("2 - no trade on spread", len(events_of_type(ev, EventType.TRADE)) == 0)

# ── 3. Exact full fill ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)
ev = e.submit_limit(Side.SELL, D("100"), 10)
trades = events_of_type(ev, EventType.TRADE)
check("3 - one trade", len(trades) == 1)
check("3 - qty 10", trades[0].qty == 10)
check("3 - price 100", trades[0].price == D("100"))
check("3 - sell doesn't rest", len(events_of_type(ev, EventType.ORDER_CREATED)) == 0)

# ── 4. Partial fill, remainder rests ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 5)
ev = e.submit_limit(Side.SELL, D("100"), 8)
trades = events_of_type(ev, EventType.TRADE)
created = events_of_type(ev, EventType.ORDER_CREATED)
check("4 - trade qty 5", trades[0].qty == 5)
check("4 - remainder 3 rests", created[0].qty == 3)

# ── 5. Price-time priority: earlier order fills first ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 5)   # id_1
e.submit_limit(Side.BUY, D("100"), 5)   # id_2
ev = e.submit_limit(Side.SELL, D("100"), 5)
trades = events_of_type(ev, EventType.TRADE)
check("5 - first order matched", trades[0].buyer_id == "id_1")

# ── 6. Better price fills before earlier time ──
e = fresh()
e.submit_limit(Side.BUY, D("99"), 5)    # id_1
e.submit_limit(Side.BUY, D("101"), 5)   # id_2
ev = e.submit_limit(Side.SELL, D("99"), 5)
trades = events_of_type(ev, EventType.TRADE)
check("6 - higher bid fills first", trades[0].buyer_id == "id_2")
check("6 - fills at resting price 101", trades[0].price == D("101"))

# ── 7. Market order full fill ──
e = fresh()
e.submit_limit(Side.SELL, D("50"), 10)
ev = e.submit_market(Side.BUY, 10)
trades = events_of_type(ev, EventType.TRADE)
check("7 - market fills fully", trades[0].qty == 10)
check("7 - no rejection", len(events_of_type(ev, EventType.ORDER_REJECTED)) == 0)

# ── 8. Market order partial fill, remainder rejected ──
e = fresh()
e.submit_limit(Side.SELL, D("50"), 3)
ev = e.submit_market(Side.BUY, 10)
trades = events_of_type(ev, EventType.TRADE)
rejected = events_of_type(ev, EventType.ORDER_REJECTED)
check("8 - trade qty 3", trades[0].qty == 3)
check("8 - rejected qty 7", rejected[0].qty == 7)

# ── 9. Market into empty book ──
e = fresh()
ev = e.submit_market(Side.BUY, 5)
check("9 - all rejected", events_of_type(ev, EventType.ORDER_REJECTED)[0].qty == 5)
check("9 - no trades", len(events_of_type(ev, EventType.TRADE)) == 0)

# ── 10. Cancel a resting order ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)  # id_1
ev = e.cancel_order("id_1")
check("10 - cancelled", ev[0].event_type == EventType.ORDER_CANCELLED)
# selling into it should not match
ev2 = e.submit_limit(Side.SELL, D("100"), 5)
check("10 - no trade after cancel", len(events_of_type(ev2, EventType.TRADE)) == 0)

# ── 11. Cancel nonexistent order ──
e = fresh()
ev = e.cancel_order("id_999")
check("11 - error on bad cancel", ev[0].event_type == EventType.ERROR)

# ── 12. Double cancel ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)
e.cancel_order("id_1")
ev = e.cancel_order("id_1")
check("12 - second cancel errors", ev[0].event_type == EventType.ERROR)

# ── 13. Amend price causes fill ──
e = fresh()
e.submit_limit(Side.SELL, D("100"), 5)  # id_1
e.submit_limit(Side.BUY, D("90"), 5)    # id_2
# amend buy up to 100 => should cross
ev = e.amend_order("id_2", new_price=D("100"))
trades = events_of_type(ev, EventType.TRADE)
check("13 - amend triggers trade", len(trades) == 1)
check("13 - trade qty 5", trades[0].qty == 5)

# ── 14. Amend loses time priority ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 5)   # id_1
e.submit_limit(Side.BUY, D("100"), 5)   # id_2
e.amend_order("id_1", new_qty=5)         # id_1 goes to back of queue
ev = e.submit_limit(Side.SELL, D("100"), 5)
trades = events_of_type(ev, EventType.TRADE)
check("14 - id_2 fills first after id_1 amended", trades[0].buyer_id == "id_2")

# ── 15. Pegged sell crosses resting buy at same price ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)  # id_1, bid=100
ev = e.submit_pegged(Side.SELL, PegSide.BID, 5)  # pegged to bid=100, crosses buy
trades = events_of_type(ev, EventType.TRADE)
check("15 - pegged sell fills against buy", len(trades) == 1)
check("15 - trade price is bid", trades[0].price == D("100"))
check("15 - trade qty 5", trades[0].qty == 5)

# ── 16. Pegged order rests when no counterparty ──
e = fresh()
e.submit_limit(Side.SELL, D("100"), 10)  # id_1, sets offer but no bid
ev = e.submit_pegged(Side.SELL, PegSide.BID, 5)  # pegged to bid, but no bid exists
check("16 - pegged rests (no opposing liquidity)", len(events_of_type(ev, EventType.ORDER_PEGGED)) == 1)

# ── 17. Pegged amend qty ──
# pegged buy rests on buy side (no sells to cross)
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)            # id_1, bid=100
e.submit_pegged(Side.BUY, PegSide.BID, 5)         # id_2, rests on buy side
ev = e.amend_order("id_2", new_qty=3)
amended = events_of_type(ev, EventType.ORDER_AMENDED)
check("17 - pegged amend succeeds", len(amended) == 1)
check("17 - new qty is 3", amended[0].qty == 3)

# ── 18. Pegged amend rejects price change ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)            # id_1
e.submit_pegged(Side.BUY, PegSide.BID, 5)         # id_2
ev = e.amend_order("id_2", new_price=D("99"))
check("18 - price on pegged errors", ev[0].event_type == EventType.ERROR)

# ── 19. Pegged amend loses priority ──
# small limit sets offer, two pegged sells, amend first, add big limit as anchor
e = fresh()
e.submit_limit(Side.SELL, D("100"), 1)             # id_1, offer=100 (seq=1)
e.submit_pegged(Side.SELL, PegSide.OFFER, 5)      # id_2, pegged at 100 (seq=2)
e.submit_pegged(Side.SELL, PegSide.OFFER, 5)      # id_3, pegged at 100 (seq=3)
e.amend_order("id_2", new_qty=5)                   # id_2 seq bumped (seq=4)
e.submit_limit(Side.SELL, D("100"), 100)           # id_4, anchor to keep offer=100 (seq=5)
# market buy 11: id_1(1), then id_3(5, seq=3) before id_2(5, seq=4)
ev = e.submit_market(Side.BUY, 11)
trades = events_of_type(ev, EventType.TRADE)
check("19 - three fills", len(trades) == 3)
check("19 - id_3 fills before amended id_2", trades[1].seller_id == "id_3")
check("19 - id_2 fills last", trades[2].seller_id == "id_2")

# ── 20. Pegged amend with no opposing liquidity ──
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)            # id_1, bid=100
e.submit_pegged(Side.BUY, PegSide.BID, 5)         # id_2, rests (no sells)
ev = e.amend_order("id_2", new_qty=8)
trades = events_of_type(ev, EventType.TRADE)
amended = events_of_type(ev, EventType.ORDER_AMENDED)
check("20 - no trade on amend with empty opposite", len(trades) == 0)
check("20 - amended to 8", amended[0].qty == 8)

# ── 21. Amend fully filled pegged ──
# pegged sell crosses buy immediately on submission => consumed
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)            # id_1
e.submit_pegged(Side.SELL, PegSide.BID, 5)        # id_2, crosses id_1 and fills
ev = e.amend_order("id_2")
check("21 - amend dead pegged errors", ev[0].event_type == EventType.ERROR)

# ── 22. Pegged amend qty down, verify fill respects new qty ──
# pegged buy rests, amend down, then market sell consumes it
e = fresh()
e.submit_limit(Side.BUY, D("100"), 10)            # id_1, bid=100
e.submit_pegged(Side.BUY, PegSide.BID, 10)        # id_2, rests on buy side
e.amend_order("id_2", new_qty=3)                   # shrink to 3
e.submit_limit(Side.BUY, D("100"), 10)            # id_3, keeps bid=100 alive
ev = e.submit_market(Side.SELL, 13)
trades = events_of_type(ev, EventType.TRADE)
# id_1 fills 10 (earliest seq), then id_2 fills 3 (amended qty, earlier seq than id_3)
check("22 - two fills", len(trades) == 2)
check("22 - first fill drains id_1", trades[0].buyer_id == "id_1" and trades[0].qty == 10)
check("22 - second fill respects amended qty", trades[1].buyer_id == "id_2" and trades[1].qty == 3)

# ── 23. Market order can't be amended ──
e = fresh()
e.submit_limit(Side.SELL, D("100"), 10)
e.submit_market(Side.BUY, 5)                      # id_2, fills immediately
ev = e.amend_order("id_2", new_qty=3)
check("23 - market amend errors", ev[0].event_type == EventType.ERROR)

# ── 24. Incoming sell sweeps multiple buy levels ──
e = fresh()
e.submit_limit(Side.BUY, D("102"), 3)              # id_1
e.submit_limit(Side.BUY, D("101"), 4)              # id_2
e.submit_limit(Side.BUY, D("100"), 5)              # id_3
ev = e.submit_limit(Side.SELL, D("100"), 10)
trades = events_of_type(ev, EventType.TRADE)
# sweeps best price first: 102 (3), 101 (4), 100 (3 of 5)
check("24 - three fills", len(trades) == 3)
check("24 - best price first", trades[0].price == D("102") and trades[0].qty == 3)
check("24 - second level", trades[1].price == D("101") and trades[1].qty == 4)
check("24 - third level partial", trades[2].price == D("100") and trades[2].qty == 3)

# ── 25. Pegged has time priority over later limit at same effective price ──
# pegged sell (pegged to offer) rests on sell side, then a limit sell arrives later
e = fresh()
e.submit_limit(Side.SELL, D("100"), 10)            # id_1, offer=100
e.submit_pegged(Side.SELL, PegSide.OFFER, 5)      # id_2, pegged at offer=100 (seq=2)
e.submit_limit(Side.SELL, D("100"), 5)             # id_3, limit at 100 (seq=3)
# market buy 15: id_1 first (seq=1), then id_2 (seq=2) before id_3 (seq=3)
ev = e.submit_market(Side.BUY, 15)
trades = events_of_type(ev, EventType.TRADE)
check("25 - two fills", len(trades) == 2)
check("25 - pegged fills before later limit", trades[1].seller_id == "id_2")


# ── Results ──
print(f"\n{'='*30}")
print(f"  {passed} passed, {failed} failed")
print(f"{'='*30}")
