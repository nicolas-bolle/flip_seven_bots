"""Write bug reports describing a table, and rebuild games from them."""

import json
from collections.abc import Mapping
from datetime import datetime
from functools import partial
from pathlib import Path

from flip_seven_bots.bots import Bot, ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionType,
    ChooseCard,
    ChooseTarget,
    FlipSevenBonus,
    VengeanceRules,
)
from flip_seven_bots.game.replay import REPORT_FORMAT
from flip_seven_bots.game.replay import replay as replay  # noqa: PLC0414
from flip_seven_bots.game.rules import (
    build_deck,
    build_vengeance_deck,
    score_cards,
    score_vengeance_cards,
)
from flip_seven_bots.provenance import git_commit

from ..common.text import card_label, event_text
from .table import Move, Table


def describe_bot(bot: Bot | None) -> str:
    """Return a readable seat controller and its relevant configuration."""
    match bot:
        case None:
            return "human"
        case ThresholdBot(threshold=threshold):
            return f"ThresholdBot({threshold})"
        case _:
            return type(bot).__name__


_git_commit = git_commit


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _action_text(action: Action, names: tuple[str, ...]) -> str:
    if action.kind is ActionType.CHOOSE_CARD:
        assert action.target is not None and action.card_index is not None
        return f"choose {names[action.target]}'s card at index {action.card_index}"
    if action.target is not None:
        return f"choose {names[action.target]}"
    return action.kind.name.lower()


def _move_json(move: Move) -> dict[str, object]:
    data: dict[str, object] = {
        "player": move.player,
        "action": move.action.kind.name.lower(),
    }
    if move.action.target is not None:
        data["target"] = move.action.target
    if move.action.card_index is not None:
        data["card_index"] = move.action.card_index
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
    if not table.replayable:
        return False
    if isinstance(rules, VengeanceRules):
        scoring = rules.score_cards
        if rules.brutal:
            valid_score = (
                isinstance(scoring, partial)
                and scoring.func is score_vengeance_cards
                and not scoring.args
                and scoring.keywords == {"brutal": True}
            )
        else:
            valid_score = scoring is score_vengeance_cards
        return rules.build_deck is build_vengeance_deck and valid_score
    return rules.build_deck is build_deck and rules.score_cards is score_cards


def _status(table: Table) -> str:
    game = table.game
    observation = table.observation
    if game.is_finished:
        return "Game over; winners: " + ", ".join(table.names[i] for i in game.winners)
    player = observation.current_player
    assert player is not None  # unfinished games await a decision
    match observation.decision:
        case ChooseCard(card=card):
            decision = f"choose a card for {card_label(card)}"
        case FlipSevenBonus():
            decision = "take the Flip 7 bonus or subtract it from a player"
        case ChooseTarget(card=card):
            decision = f"choose a player for {card_label(card)}"
        case _:
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
    mode = (
        "With a Vengeance (Brutal Mode)"
        if isinstance(rules, VengeanceRules) and rules.brutal
        else "With a Vengeance"
        if isinstance(rules, VengeanceRules)
        else "Flip 7"
    )
    seed = "random" if table.seed is None else str(table.seed)
    lines += [
        "## Table",
        "",
        f"- **Table seed:** {seed}; **game seed:** {table.game_seed}",
        f"- **Mode:** {mode}",
        (
            f"- **Rules:** target score {rules.target_score}, "
            f"Flip 7 bonus {rules.flip_seven_bonus}"
        ),
        "",
        "| Seat | Name | Player | Status | Cards | Unresolved | Round score | Total |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for view in observation.players:
        seat = table.seats[view.player]
        cards = ", ".join(card_label(card) for card in view.cards) or "-"
        unresolved = ", ".join(card_label(card) for card in view.unresolved) or "-"
        lines.append(
            f"| {view.player} | {_cell(seat.name)} | {describe_bot(seat.bot)} "
            f"| {view.status.name.lower()} | {cards} | {unresolved} "
            f"| {view.round_score} | {view.total_score} |"
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
            f"{names[i]} {score:+d} (total {total})"
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
        replay_data: dict[str, object] = {
            "format": 2 if isinstance(rules, VengeanceRules) else REPORT_FORMAT,
            "players": len(table.seats),
            "game_seed": table.game_seed,
            "starting_dealer": table.starting_dealer,
            "target_score": rules.target_score,
            "flip_seven_bonus": rules.flip_seven_bonus,
        }
        if isinstance(rules, VengeanceRules):
            replay_data["mode"] = "vengeance"
            replay_data["brutal"] = rules.brutal
        lines += [
            (
                f"{len(table.moves)} moves so far. Rebuild the game with "
                "`flip_seven_bots.game.replay.replay(path)`."
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
