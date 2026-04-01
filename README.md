# Matching Engine

A financial order matching engine built in Python. It supports multiple order types, price-time priority, and an interactive command-line interface.

## Features

- **Limit orders** — resting orders with a specified price
- **Market orders** — execute immediately against resting liquidity; unfilled quantity is rejected
- **Pegged orders** — track the best bid or best offer dynamically
- **Cancel & amend** — remove or modify resting orders (amended orders lose time priority)
- **Price-time priority** — orders are matched by best price first, then by arrival sequence

## Usage

```
python main.py
```

### Commands

| Command | Example | Description |
|---|---|---|
| `limit <side> <price> <qty>` | `limit buy 100 10` | Place a limit order |
| `market <side> <qty>` | `market sell 5` | Place a market order |
| `peg <side> <bid\|offer> <qty>` | `peg buy bid 10` | Place a pegged order |
| `cancel <order_id>` | `cancel id_1` | Cancel a resting order |
| `amend <id> price <p> qty <q>` | `amend id_1 price 101 qty 5` | Amend price and/or quantity |
| `print book` | `print book` | Display the order book |
| `quit` | `quit` | Exit |

The engine has a `detailed` flag (set in `main.py`). When off, trade output is aggregated and partial market rejections are hidden. Order IDs are always shown on creation.

### Example session

```
>>> limit buy 100 10
Order created: buy 10 @ 100 id_1
>>> limit sell 99 5
Trade, price: 100, qty: 5
>>> print book
=== ORDER BOOK ===
  Best bid: 100  Best offer: None
--- SELL ---
--- BUY ---
  5 @ 100
>>> quit
```

## Architecture

```
parser.py        Tokenizes input into typed command objects
main.py          CLI loop and command dispatch
models.py        Data models (Order, EngineEvent, enums)
book.py          Order book structure (BookSide, price levels)
engine.py        Core matching logic and order lifecycle
```

## Data Structure

The order book is built around two core structures:

- **`SortedList`** of price levels — keeps prices ordered so the best bid/offer is always accessible by index. New price levels are inserted in sorted position; empty levels are removed.
- **Doubly linked list** per price level — maintains FIFO order among orders at the same price. Each `Order` holds a back-pointer to its own node in the list, enabling direct access without traversal.

Pegged orders live in separate linked lists (one for peg to the bid, one for peg to the offer) and are evaluated against the current best bid/offer at match time.

During matching, the engine compares the top candidate from each queue (best limit level, peg-bid, peg-offer), picks the one with the best effective price (breaking ties by arrival sequence), and executes the trade.