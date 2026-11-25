"""Plain-text descriptions shared by the screens and bug reports."""

from collections.abc import Sequence

from flip_seven_bots.game import (
    ActionChosen,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    DiscardShuffled,
    GameEvent,
    RoundEnded,
    RoundStarted,
)


def card_label(card: Card) -> str:
    """Return the compact display label for a card."""
    match card.kind:
        case CardType.NUMBER:
            return str(card.value)
        case CardType.ADD:
            return f'+{card.value}'
        case CardType.MULTIPLY:
            return f'x{card.value}'
        case CardType.FREEZE:
            return 'FREEZE'
        case CardType.FLIP_THREE:
            return 'FLIP 3'
        case CardType.SECOND_CHANCE:
            return 'SECOND CHANCE'
        case CardType.ZERO:
            return 'ZERO'
        case CardType.UNLUCKY_SEVEN:
            return 'UNLUCKY 7'
        case CardType.LUCKY_THIRTEEN:
            return 'LUCKY 13'
        case CardType.SUBTRACT:
            return f'-{card.value}'
        case CardType.DIVIDE:
            return '/2'
        case CardType.JUST_ONE_MORE:
            return 'ONE MORE'
        case CardType.FLIP_FOUR:
            return 'FLIP 4'
        case CardType.SWAP:
            return 'SWAP'
        case CardType.STEAL:
            return 'STEAL'
        case CardType.DISCARD:
            return 'DISCARD'


def event_text(event: GameEvent, names: Sequence[str]) -> str:
    """Describe a public event using names indexed by player ID."""
    match event:
        case RoundStarted(round_number=round_number):
            return f'Round {round_number} started'
        case DiscardShuffled():
            return 'Discard pile reshuffled'
        case RoundEnded(result=result):
            if result.flip_seven_player is not None:
                return f'{names[result.flip_seven_player]} got Flip 7!'
            return f'Round {result.round_number} ended'
        case CardDrawn(player=player, card=card):
            return f'{names[player]} drew {card_label(card)}'
        case ActionChosen(player=player, action=action):
            if action.kind is ActionType.CHOOSE_CARD:
                assert action.target is not None and action.card_index is not None
                return f'{names[player]} chose a card from {names[action.target]}'
            if action.kind is ActionType.TAKE_BONUS:
                return f'{names[player]} took the bonus'
            if action.target is not None:
                return f'{names[player]} chose {names[action.target]}'
            return f'{names[player]} chose {action.kind.name.lower()}'
