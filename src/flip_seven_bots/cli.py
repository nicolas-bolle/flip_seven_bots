"""Discoverable entry point for the game and tournament interfaces."""

import argparse
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game import Action, Observation, Rules


def _tournament(argv: list[str]) -> None:
    from .tournament.cli import parse_launch

    launch = parse_launch(argv)
    if launch.gui:
        from .gui.tournament.app import main as window

        window(launch.options, show_setup=launch.show_setup)
    else:
        from .tournament.cli import run

        run(launch.options)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="flip7", description="Flip 7 games and bot experiments"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("play", help="play in a window", add_help=False)
    commands.add_parser("tournament", help="run a tournament", add_help=False)
    commands.add_parser("bots", help="list available bots")
    replay = commands.add_parser("replay", help="rebuild a game from a bug report")
    replay.add_argument("report")
    replay.add_argument("--moves", type=int, help="replay only this many moves")
    compare = commands.add_parser("compare", help="compare two bot specifications")
    compare.add_argument("first")
    compare.add_argument("second")
    trace = commands.add_parser("trace", help="inspect a bot's decisions in one game")
    trace.add_argument("--bot", action="append", metavar="[NAME=]KIND")
    trace.add_argument(
        "--seat", type=int, default=0, help="seat to inspect (default: 0)"
    )
    trace.add_argument("--seed", type=int, default=1)
    trace.add_argument(
        "--step", action="store_true", help="wait for Enter after each decision"
    )
    trace.add_argument("--vengeance", action="store_true")
    trace.add_argument("--brutal", action="store_true")
    args, rest = parser.parse_known_args(argv)
    if args.command == "play":
        from .gui.play.app import main as play

        play(rest)
    elif args.command == "tournament":
        _tournament(rest)
    elif args.command == "compare":
        _tournament(["--bot", args.first, "--bot", args.second, *rest])
    elif args.command == "bots":
        if rest:
            parser.error(f"unrecognized arguments: {' '.join(rest)}")
        from .bots.registry import kinds

        for kind in kinds():
            params = ", ".join(f"{p.name}={p.default}" for p in kind.parameters)
            print(f"{kind.kind:12} {kind.label}" + (f" ({params})" if params else ""))
    elif args.command == "trace":
        if rest:
            parser.error(f"unrecognized arguments: {' '.join(rest)}")
        from random import Random

        from .bots.registry import config_for
        from .bots.specs import parse_named_bot
        from .game import VengeanceRules
        from .simulation import play_game

        try:
            named = [
                parse_named_bot(spec)
                for spec in (args.bot or ["threshold:30", "random"])
            ]
        except ValueError as error:
            parser.error(str(error))
        if not 0 <= args.seat < len(named):
            parser.error("--seat must identify a bot")
        rng = Random(args.seed)
        bots = [config_for(bot)(rng.getrandbits(64)) for _, bot in named]
        bot = bots[args.seat]

        class TracedBot:
            def choose_action(self, observation: Observation) -> Action:
                action = bot.choose_action(observation)
                print(
                    f"Round {observation.round_number}, seat {observation.player}: "
                    f"{observation.decision!r} -> {action!r}"
                )
                if args.step:
                    input("Press Enter for the next decision...")
                return action

            def on_game_start(self, seat: int, count: int, rules: Rules) -> None:
                hook = getattr(bot, "on_game_start", None)
                if hook is not None:
                    hook(seat, count, rules)

            def on_game_end(self, observation: Observation) -> None:
                hook = getattr(bot, "on_game_end", None)
                if hook is not None:
                    hook(observation)

        bots[args.seat] = TracedBot()
        rules = (
            VengeanceRules(brutal=args.brutal)
            if args.vengeance or args.brutal
            else None
        )
        result = play_game(bots, seed=args.seed, rules=rules)
        print(
            f"Winners: {result.winners}; scores: "
            + ", ".join(str(player.total_score) for player in result.players)
        )
    else:
        if rest:
            parser.error(f"unrecognized arguments: {' '.join(rest)}")
        from .game.replay import replay as replay_game

        game = replay_game(args.report, moves=args.moves)
        observation = game.observe(game.current_player or 0)
        print(
            f"Round {observation.round_number}; scores: "
            + ", ".join(str(player.total_score) for player in observation.players)
        )
        print(
            f"Current player: {observation.current_player}; winners: {observation.winners}"
        )
