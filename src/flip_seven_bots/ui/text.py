"""Plain-text descriptions shared by the screen and bug reports."""

from collections.abc import Sequence

from flip_seven_bots.game import (
    ActionChosen,
    Card,
    CardDrawn,
    CardType,
    DiscardShuffled,
    GameEvent,
    RoundEnded,
    RoundStarted,
)


def card_label(card: Card) -> str:
    match card.kind:
        case CardType.NUMBER:
            return str(card.value)
        case CardType.ADD:
            return f"+{card.value}"
        case CardType.MULTIPLY:
            return f"x{card.value}"
        case CardType.FREEZE:
            return "FREEZE"
        case CardType.FLIP_THREE:
            return "FLIP 3"
        case CardType.SECOND_CHANCE:
            return "SECOND CHANCE"


def event_text(event: GameEvent, names: Sequence[str]) -> str:
    match event:
        case RoundStarted(round_number=round_number):
            return f"Round {round_number} started"
        case DiscardShuffled():
            return "Discard pile reshuffled"
        case RoundEnded(result=result):
            if result.flip_seven_player is not None:
                return f"{names[result.flip_seven_player]} got Flip 7!"
            return f"Round {result.round_number} ended"
        case CardDrawn(player=player, card=card):
            return f"{names[player]} drew {card_label(card)}"
        case ActionChosen(player=player, action=action):
            if action.target is not None:
                return f"{names[player]} chose {names[action.target]}"
            return f"{names[player]} chose {action.kind.name.lower()}"
