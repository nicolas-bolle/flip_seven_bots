"""Rebuild games from the replay data in bug reports."""

import json
import re
from pathlib import Path

from .engine import Game
from .model import Action, ActionType
from .rules import Rules, VengeanceRules

REPORT_FORMAT = 1
_REPLAY_BLOCK = re.compile(
    r"^## Replay$.*?^```json\n(.*?)^```$", re.MULTILINE | re.DOTALL
)


def replay(report: Path | str, *, moves: int | None = None) -> Game:
    """Rebuild the reported game by replaying its first ``moves`` moves."""
    if moves is not None and moves < 0:
        raise ValueError("moves must not be negative")
    blocks = _REPLAY_BLOCK.findall(Path(report).read_text(encoding="utf-8"))
    if not blocks:
        raise ValueError("report has no replay data")
    data = json.loads(blocks[-1])
    if data["format"] not in (REPORT_FORMAT, 2):
        raise ValueError(f"unsupported report format: {data['format']}")
    if data["format"] == 2:
        if data.get("mode") != "vengeance" or not isinstance(data.get("brutal"), bool):
            raise ValueError("invalid Vengeance replay rules")
        rules = VengeanceRules(
            target_score=data["target_score"],
            flip_seven_bonus=data["flip_seven_bonus"],
            brutal=data["brutal"],
        )
    else:
        rules = Rules(
            target_score=data["target_score"], flip_seven_bonus=data["flip_seven_bonus"]
        )
    game = Game(
        data["players"],
        seed=data["game_seed"],
        dealer=data["starting_dealer"],
        rules=rules,
    )
    for index, move in enumerate(data["moves"][:moves], start=1):
        if game.current_player != move["player"]:
            raise ValueError(
                f"replay diverged at move {index}: expected player {move['player']}, "
                f"game is waiting for {game.current_player}"
            )
        game.apply(
            Action(
                ActionType[move["action"].upper()],
                move.get("target"),
                move.get("card_index"),
            )
        )
    return game
