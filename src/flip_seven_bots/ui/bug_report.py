"""Write bug reports describing a table, and rebuild games from them."""

import json
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from flip_seven_bots.bots import Bot, FlipThreeMonteCarloBot, ThresholdBot
from flip_seven_bots.game import Action, ActionType, Game, Rules
from flip_seven_bots.game.rules import build_deck, score_cards

from .table import Move, Table
from .text import card_label, event_text

REPORT_FORMAT = 1
_REPLAY_BLOCK = re.compile(
    r"^## Replay$.*?^```json\n(.*?)^```$", re.MULTILINE | re.DOTALL
)


def describe_bot(bot: Bot | None) -> str:
    match bot:
        case None:
            return "human"
        case ThresholdBot(threshold=threshold):
            return f"ThresholdBot({threshold})"
        case FlipThreeMonteCarloBot(
            fallback=fallback, rollout=rollout, samples=samples
        ):
            return (
                f"FlipThreeMonteCarloBot(fallback={describe_bot(fallback)}, "
                f"rollout={describe_bot(rollout)}, samples={samples})"
            )
        case _:
            return type(bot).__name__


def _git_commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "--short", "HEAD")
        dirty = git("status", "--porcelain")
    except OSError, subprocess.SubprocessError:
        return "unknown"
    return f"{commit} (with uncommitted changes)" if dirty else commit


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _action_text(action: Action, names: tuple[str, ...]) -> str:
    if action.target is not None:
        return f"give to {names[action.target]}"
    return action.kind.name.lower()


def _move_json(move: Move) -> dict[str, object]:
    data: dict[str, object] = {
        "player": move.player,
        "action": move.action.kind.name.lower(),
    }
    if move.action.target is not None:
        data["target"] = move.action.target
    return data


def _replay_json(data: Mapping[str, object], moves: list[Move]) -> str:
    """Pretty-print replay data with one move per line, so long games stay readable."""
    fields = [
        f"  {json.dumps(key)}: {json.dumps(value)}" for key, value in data.items()
    ]
    move_lines = ",\n".join(f"    {json.dumps(_move_json(move))}" for move in moves)
    fields.append(f'  "moves": [\n{move_lines}\n  ]' if moves else '  "moves": []')
    return "{\n" + ",\n".join(fields) + "\n}"


def _replayable(table: Table) -> bool:
    rules = table.game.rules
    return (
        table.replayable
        and rules.build_deck is build_deck
        and rules.score_cards is score_cards
    )


def _status(table: Table) -> str:
    game = table.game
    observation = table.observation
    if game.is_finished:
        return "Game over; winners: " + ", ".join(table.names[i] for i in game.winners)
    player = observation.current_player
    assert player is not None  # unfinished games await a decision
    if observation.pending_card is not None:
        decision = f"choose a player for {card_label(observation.pending_card)}"
    else:
        decision = "hit or stay"
    status = f"Waiting for {table.names[player]} to {decision}"
    if table.round_summary is not None:
        status += f" (round {table.round_summary.round_number} summary on screen)"
    return status


def report_markdown(
    table: Table, message: str, *, created: datetime, error: str | None = None
) -> str:
    """Describe the table's current game, including hidden information, as Markdown."""
    game = table.game
    names = table.names
    observation = table.observation
    lines = [
        "# Flip 7 bug report",
        "",
        f"- **Reported:** {created:%Y-%m-%d %H:%M:%S}",
        f"- **Commit:** {_git_commit()}",
        "",
        "## Message",
        "",
        message.strip() or "(no message)",
        "",
    ]
    if error is not None:
        lines += ["## Error", "", "```text", error.rstrip(), "```", ""]

    rules = game.rules
    seed = "random" if table.seed is None else str(table.seed)
    lines += [
        "## Table",
        "",
        f"- **Table seed:** {seed}; **game seed:** {table.game_seed}",
        (
            f"- **Rules:** target score {rules.target_score}, "
            f"Flip 7 bonus {rules.flip_seven_bonus}"
        ),
        "",
        "| Seat | Name | Player | Status | Cards | Round score | Total |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for view in observation.players:
        seat = table.seats[view.player]
        cards = ", ".join(card_label(card) for card in view.cards) or "-"
        lines.append(
            f"| {view.player} | {_cell(seat.name)} | {describe_bot(seat.bot)} "
            f"| {view.status.name.lower()} | {cards} | {view.round_score} "
            f"| {view.total_score} |"
        )

    lines += [
        "",
        "## Current state",
        "",
        f"- **Round:** {observation.round_number}; **dealer:** {names[observation.dealer]}",
        f"- **Status:** {_status(table)}",
    ]
    if observation.legal_actions:
        actions = ", ".join(_action_text(a, names) for a in observation.legal_actions)
        lines.append(f"- **Legal actions:** {actions}")
    if observation.last_round is not None:
        result = observation.last_round
        scores = ", ".join(
            f"{names[i]} +{score} (total {total})"
            for i, (score, total) in enumerate(zip(result.scores, result.totals))
        )
        lines.append(f"- **Last round ({result.round_number}):** {scores}")
    discard = ", ".join(card_label(card) for card in observation.discard) or "empty"
    lines += [f"- **Discard pile:** {discard}", "", "### This round's events", ""]
    lines += [
        f"{index}. {event_text(event, names)}"
        for index, event in enumerate(observation.events, start=1)
    ]

    deck = game.hidden_deck()
    lines += [
        "",
        "## Hidden deck",
        "",
        f"<details><summary>{len(deck)} cards, next card first</summary>",
        "",
        ", ".join(card_label(card) for card in deck) or "empty",
        "",
        "</details>",
        "",
        "## Replay",
        "",
    ]
    if _replayable(table):
        replay_data = {
            "format": REPORT_FORMAT,
            "players": len(table.seats),
            "game_seed": table.game_seed,
            "starting_dealer": table.starting_dealer,
            "target_score": rules.target_score,
            "flip_seven_bonus": rules.flip_seven_bonus,
        }
        lines += [
            (
                f"{len(table.moves)} moves so far. Rebuild the game with "
                "`flip_seven_bots.ui.bug_report.replay(path)`."
            ),
            "",
            "```json",
            _replay_json(replay_data, list(table.moves)),
            "```",
        ]
    else:
        lines.append("Not available: this table used a custom deck or game factory.")
    return "\n".join(lines) + "\n"


def write_report(
    table: Table,
    message: str,
    directory: Path,
    *,
    error: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Write a report to a new, timestamped Markdown file in ``directory``."""
    created = now if now is not None else datetime.now()
    text = report_markdown(table, message, created=created, error=error)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{created:%Y-%m-%d_%H-%M-%S}" + ("_crash" if error is not None else "")
    for attempt in range(1, 1000):
        path = directory / (f"{stem}.md" if attempt == 1 else f"{stem}-{attempt}.md")
        try:
            with path.open("x", encoding="utf-8") as file:
                file.write(text)
        except FileExistsError:
            continue
        return path
    raise FileExistsError(f"too many reports named {stem} in {directory}")


def replay(report: Path | str, *, moves: int | None = None) -> Game:
    """Rebuild the reported game by replaying its first ``moves`` moves (default: all).

    A crash report's last move is the one that failed, so replaying all moves
    reproduces the crash.
    """
    # The last block is used so a user's message can't stand in for the real one.
    blocks = _REPLAY_BLOCK.findall(Path(report).read_text(encoding="utf-8"))
    if not blocks:
        raise ValueError("report has no replay data")
    data = json.loads(blocks[-1])
    if data["format"] != REPORT_FORMAT:
        raise ValueError(f"unsupported report format: {data['format']}")
    game = Game(
        data["players"],
        seed=data["game_seed"],
        dealer=data["starting_dealer"],
        rules=Rules(
            target_score=data["target_score"], flip_seven_bonus=data["flip_seven_bonus"]
        ),
    )
    for index, move in enumerate(data["moves"][:moves], start=1):
        if game.current_player != move["player"]:
            raise ValueError(
                f"replay diverged at move {index}: expected player {move['player']}, "
                f"game is waiting for {game.current_player}"
            )
        game.apply(Action(ActionType[move["action"].upper()], move.get("target")))
    return game
