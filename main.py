from parser import (AmendCommand, CancelCommand, LimitCommand,
                    MarketCommand, PeggedCommand, PrintBookCommand,
                    QuitCommand, parse_command)
from engine import MatchingEngine
from models import EventType, aggregate_trades


def main():
    engine = MatchingEngine()
    detailed = False

    handlers = {
        LimitCommand: lambda c: engine.submit_limit(c.side, c.price, c.qty),
        MarketCommand: lambda c: engine.submit_market(c.side, c.qty),
        CancelCommand: lambda c: engine.cancel_order(c.order_id),
        AmendCommand: lambda c: engine.amend_order(c.order_id, c.new_price, c.new_qty),
        PeggedCommand: lambda c: engine.submit_pegged(c.side, c.peg_side, c.qty),
    }

    while True:
        try:
            cmd = parse_command(input(">>> ").strip())

            if isinstance(cmd, QuitCommand):
                break
            if isinstance(cmd, PrintBookCommand):
                print(engine.book.format_book(detailed))
                continue

            events = handlers[type(cmd)](cmd)
            if not detailed:
                events = aggregate_trades(events)
                events = [e for e in events if e.event_type != EventType.ORDER_REJECTED]
            for event in events:
                print(event.render(detailed))

        except ValueError as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()