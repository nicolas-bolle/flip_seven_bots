"""Run a tournament in the background and show live progress, standings, and ratings."""

import math
import queue
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import pygame

from flip_seven_bots.tournament import GameRecord, TournamentResult
from flip_seven_bots.tournament.config import TournamentOptions
from flip_seven_bots.tournament.storage import save_results

from ..common.theme import (
    ACCENT,
    ACTIVE,
    BACKGROUND,
    BUTTON,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)
from ..common.widgets import draw_button, draw_text

PROGRESS_BAR = pygame.Rect(90, 130, 1100, 40)
STANDINGS = pygame.Rect(90, 230, 560, 520)
CHART = pygame.Rect(680, 230, 510, 520)
STOP_BUTTON = pygame.Rect(90, 790, 200, 56)
SAVE_BUTTON = pygame.Rect(90, 790, 220, 56)
NEW_BUTTON = pygame.Rect(330, 790, 240, 56)
DEFAULT_SAVE_DIR = Path('tournament_results')
LINE_COLORS = (
    (233, 196, 106),
    (113, 207, 165),
    (231, 111, 81),
    (122, 162, 247),
    (244, 162, 97),
    (199, 146, 234),
    (240, 244, 229),
    (42, 157, 143),
    (239, 112, 160),
    (176, 216, 88),
)


@dataclass
class _Standing:
    name: str
    color: tuple[int, int, int]
    elo: float
    games: int = 0
    wins: int = 0
    place_total: int = 0


@dataclass(frozen=True)
class _Finished:
    """Queue marker: the worker played every game or was stopped, and rated them."""

    result: TournamentResult | None


class TournamentScene:
    """Play ``options`` on a worker thread and render its progress each frame.

    The worker checks for Stop between games. ``restart`` becomes true when the
    user asks for a new tournament; ``close`` stops the worker.
    """

    def __init__(
        self, options: TournamentOptions, *, save_dir: Path = DEFAULT_SAVE_DIR
    ) -> None:
        self.options = options
        self.records: list[GameRecord] = []
        self.finished = False
        self.error: str | None = None
        self.restart = False
        self.saved: tuple[Path, Path] | None = None
        self.result: TournamentResult | None = None
        """Final tables, available once ``finished`` if any game was played."""
        self._save_dir = options.output or save_dir / datetime.now().strftime(
            '%Y-%m-%d_%H-%M-%S'
        )
        self._standings = {
            name: _Standing(
                name, LINE_COLORS[index % len(LINE_COLORS)], options.initial_rating
            )
            for index, name in enumerate(options.bots)
        }
        self._history = [tuple(options.initial_rating for _ in options.bots)]
        self._queue: queue.Queue[GameRecord | _Finished | BaseException] = queue.Queue()
        self._stop = threading.Event()
        self._started = time.monotonic()
        self._elapsed = 0.0
        self._last_game_elapsed = 0.0
        self._slot_widths: dict[str, int] = {}
        self._title_font = pygame.font.Font(None, 52)
        self._heading_font = pygame.font.Font(None, 32)
        self._font = pygame.font.Font(None, 26)
        self._small_font = pygame.font.Font(None, 21)
        games = options.start()
        self._worker = threading.Thread(target=self._play, args=(games,), daemon=True)
        self._worker.start()

    @property
    def dialog_open(self) -> bool:
        """The tournament screen has no modal dialog, so Escape may quit."""
        return False

    def _play(self, games) -> None:
        try:
            played = []
            try:
                for record in games:
                    played.append(record)
                    self._queue.put(record)
                    if self._stop.is_set():
                        break
            finally:
                if isinstance(games, Generator):
                    games.close()
            # Fitting with confidence intervals can take a moment, so do it off the UI thread.
            self._queue.put(_Finished(self.options.result(played) if played else None))
        except BaseException as error:  # noqa: BLE001 - reported on screen instead
            self._queue.put(error)

    def close(self) -> None:
        """Ask the worker to stop after its current game."""
        self._stop.set()

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle Stop while running, and Save or New tournament once finished."""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if not self.finished:
            if STOP_BUTTON.collidepoint(event.pos):
                self.close()
        elif NEW_BUTTON.collidepoint(event.pos):
            self.restart = True
        elif SAVE_BUTTON.collidepoint(event.pos) and self.result and self.saved is None:
            self.saved = save_results(self.result, self._save_dir, self.options)

    def update(self, _now: int) -> None:
        """Apply every game the worker has finished since the last frame."""
        while not self.finished:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            match item:
                case GameRecord():
                    self._record(item)
                case _Finished(result=result):
                    self._finish(result)
                case BaseException():
                    self.error = f'{type(item).__name__}: {item}'
                    self._finish(None)
        if not self.finished and len(self.records) < self.options.games:
            self._elapsed = time.monotonic() - self._started

    def _record(self, record: GameRecord) -> None:
        self.records.append(record)
        self._last_game_elapsed = time.monotonic() - self._started
        for name, place, elo in zip(record.players, record.places, record.elo):
            standing = self._standings[name]
            standing.elo = elo
            standing.games += 1
            standing.wins += place == 1
            standing.place_total += place
        self._history.append(tuple(s.elo for s in self._standings.values()))

    def _finish(self, result: TournamentResult | None) -> None:
        self.finished = True
        self.result = result
        if self.options.output is not None and result is not None:
            self.saved = save_results(result, self.options.output, self.options)

    def render(
        self, screen: pygame.Surface, _mouse_pos: tuple[int, int] | None = None
    ) -> None:
        """Draw progress, standings, the rating chart, and the available buttons."""
        screen.fill(BACKGROUND)
        draw_text(screen, self._title_font, 'TOURNAMENT', (90, 45), ACCENT)
        draw_text(screen, self._font, self.options.describe(), (420, 58), MUTED)
        self._draw_progress(screen)
        self._draw_standings(screen)
        self._draw_chart(screen)
        if not self.finished:
            draw_button(
                screen, self._font, STOP_BUTTON, 'Stop', disabled=self._stop.is_set()
            )
        else:
            label = 'Saved' if self.saved else 'Save results'
            disabled = bool(self.saved or self.result is None)
            draw_button(screen, self._font, SAVE_BUTTON, label, disabled=disabled)
            draw_button(screen, self._font, NEW_BUTTON, 'New tournament', selected=True)
        if self.saved is not None:
            draw_text(
                screen,
                self._small_font,
                f'Saved to {self.saved[0].parent}',
                (600, 810),
                MUTED,
            )
        draw_text(screen, self._small_font, 'Esc quits.', (1110, 810), MUTED)

    def _draw_progress(self, screen: pygame.Surface) -> None:
        played, total = len(self.records), self.options.games
        pygame.draw.rect(screen, PANEL, PROGRESS_BAR, border_radius=8)
        filled = PROGRESS_BAR.copy()
        filled.width = round(PROGRESS_BAR.width * played / total)
        if filled.width:
            pygame.draw.rect(
                screen,
                ACTIVE if self.error is None else ACCENT,
                filled,
                border_radius=8,
            )
        font = self._font
        label = (
            ('played', str(played)),
            (None, f' / {total} games  ('),
            ('percent', f'{played / total:.0%}'),
            (None, ')'),
        )
        width = sum(self._slot_width(font, key, text) for key, text in label)
        self._draw_slots(
            screen,
            font,
            label,
            (
                PROGRESS_BAR.centerx - width // 2,
                PROGRESS_BAR.centery - font.get_height() // 2,
            ),
            TEXT,
        )

        # Measure the rate when games arrive, not every frame, so it doesn't
        # sag between games and jump back when the next one finishes.
        rate = played / self._last_game_elapsed if self._last_game_elapsed else 0.0
        status: tuple[tuple[str | None, str], ...]
        if self.error is not None:
            status = ((None, f'Stopped by an error: {self.error}'),)
        elif not self.finished:
            status = ((None, 'Running: '), ('rate', f'{rate:.1f}'), (None, ' games/s'))
            if rate:
                remaining = max(0.0, total / rate - self._elapsed)
                status += (
                    (None, ', about '),
                    ('remaining', f'{remaining:.0f}'),
                    (None, ' s left'),
                )
            if played == total:
                status = ((None, 'Computing ratings...'),)
            elif self._stop.is_set():
                status = (
                    (
                        None,
                        'Stopping after the current game, then computing ratings...',
                    ),
                )
        elif played < total:
            status = ((None, f'Stopped after {played} games in {self._elapsed:.1f} s'),)
        else:
            status = (
                (None, f'Finished in {self._elapsed:.1f} s ({rate:.1f} games/s)'),
            )
        self._draw_slots(
            screen,
            font,
            status,
            (PROGRESS_BAR.x, PROGRESS_BAR.bottom + 14),
            ACCENT if self.error else MUTED,
        )

    def _slot_width(self, font: pygame.font.Font, key: str | None, text: str) -> int:
        """Width of ``text``, or of the widest text shown so far in slot ``key``."""
        width = font.size(text)[0]
        if key is not None:
            width = self._slot_widths[key] = max(self._slot_widths.get(key, 0), width)
        return width

    def _draw_slots(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        parts: tuple[tuple[str | None, str], ...],
        pos: tuple[int, int],
        color: tuple[int, int, int],
    ) -> None:
        """Draw text pieces in a row, right-aligning each keyed piece in its slot.

        Slots only grow, so later pieces don't shift as numbers change width.
        """
        x, y = pos
        for key, text in parts:
            width = self._slot_width(font, key, text)
            if key is None:
                draw_text(screen, font, text, (x, y), color)
            else:
                draw_text(screen, font, text, (x + width, y), color, anchor='topright')
            x += width

    def _draw_standings(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, PANEL, STANDINGS, border_radius=10)
        x, y = STANDINGS.x + 18, STANDINGS.y + 16
        summary = self.result.summary if self.result is not None else None
        title = 'Final standings' if summary is not None else 'Standings (live Elo)'
        draw_text(screen, self._heading_font, title, (x, y))
        rating_label = 'RATING (95%)' if summary is not None else 'ELO'
        # Numbers are right-aligned to these edges so digits stay in place.
        columns = (
            ('BOT', 18, 'topleft'),
            (rating_label, 265, 'topright'),
            ('GAMES', 330, 'topright'),
            ('WINS', 440, 'topright'),
            ('AVG PLACE', 528, 'topright'),
        )
        for label, offset, anchor in columns:
            draw_text(
                screen,
                self._small_font,
                label,
                (x + offset, y + 44),
                MUTED,
                anchor=anchor,
            )
        if summary is not None:
            ranked = [self._standings[name] for name in summary.index]
        else:
            ranked = sorted(self._standings.values(), key=lambda s: s.elo, reverse=True)
        for row, standing in enumerate(ranked):
            row_y = y + 70 + row * 43
            if row % 2 == 0:
                stripe = (STANDINGS.x + 8, row_y - 8, STANDINGS.width - 16, 40)
                pygame.draw.rect(screen, PANEL_ALT, stripe, border_radius=6)
            pygame.draw.rect(screen, standing.color, (x, row_y + 3, 10, 14))
            draw_text(
                screen, self._font, self._fit(standing.name, 165), (x + 18, row_y)
            )
            win_rate = (
                f'({standing.wins / standing.games:.0%})' if standing.games else ''
            )
            average = (
                f'{standing.place_total / standing.games:.2f}'
                if standing.games
                else '-'
            )
            cells = (
                (self._rating_text(standing, summary), 265),
                (str(standing.games), 330),
                (str(standing.wins), 380),
                (win_rate, 440),
                (average, 528),
            )
            for text, offset in cells:
                draw_text(
                    screen,
                    self._font,
                    text,
                    (x + offset, row_y),
                    TEXT,
                    anchor='topright',
                )

    @staticmethod
    def _rating_text(standing: _Standing, summary: pd.DataFrame | None) -> str:
        if summary is None:
            return f'{standing.elo:.0f}'
        rating, low, high = summary.loc[
            standing.name, ['rating', 'rating_low', 'rating_high']
        ].to_numpy(dtype=float)
        if math.isnan(rating):  # never played
            return '-'
        if math.isnan(low):  # fewer than two deals
            return f'{rating:.0f}'
        return f'{rating:.0f} \u00b1{(high - low) / 2:.0f}'

    def _fit(self, text: str, width: int) -> str:
        """Shorten ``text`` with an ellipsis until it fits in ``width`` pixels."""
        if self._font.size(text)[0] <= width:
            return text
        while text and self._font.size(text + '...')[0] > width:
            text = text[:-1]
        return text.rstrip() + '...'

    def _draw_chart(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, PANEL, CHART, border_radius=10)
        draw_text(
            screen, self._heading_font, 'Elo by game', (CHART.x + 18, CHART.y + 16)
        )
        plot = pygame.Rect(
            CHART.x + 60, CHART.y + 64, CHART.width - 84, CHART.height - 110
        )
        low = min(min(ratings) for ratings in self._history)
        high = max(max(ratings) for ratings in self._history)
        fitted = []
        if self.result is not None:
            summary = self.result.summary
            values = summary[['rating', 'rating_low', 'rating_high']].to_numpy(
                dtype=float
            )
            for name, (rating, lower, upper) in zip(summary.index, values):
                if math.isfinite(rating):
                    fitted.append((self._standings[name].color, rating, lower, upper))
                    bounds = [
                        value
                        for value in (rating, lower, upper)
                        if math.isfinite(value)
                    ]
                    low, high = min(low, *bounds), max(high, *bounds)
        gutter = 10 * min(len(fitted), len(LINE_COLORS))
        if fitted:
            plot.width -= gutter + 6
            draw_text(
                screen,
                self._small_font,
                'Dashed: fitted rating   |   Bars: 95% confidence interval',
                (CHART.x + 18, CHART.y + 43),
                MUTED,
            )
        padding = max(10.0, (high - low) * 0.1)
        low, high = low - padding, high + padding
        games = max(len(self._history) - 1, 1)

        def point(game: int, rating: float) -> tuple[int, int]:
            return (
                plot.x + round(plot.width * game / games),
                plot.bottom - round(plot.height * (rating - low) / (high - low)),
            )

        for fraction in (0, 0.5, 1):
            rating = low + (high - low) * fraction
            y = point(0, rating)[1]
            pygame.draw.line(screen, PANEL_ALT, (plot.x, y), (plot.right, y))
            draw_text(
                screen,
                self._small_font,
                f'{rating:.0f}',
                (plot.x - 8, y - 7),
                MUTED,
                anchor='topright',
            )
        draw_text(screen, self._small_font, '0', (plot.x - 4, plot.bottom + 10), MUTED)
        draw_text(
            screen,
            self._small_font,
            str(games),
            (plot.right, plot.bottom + 10),
            MUTED,
            anchor='topright',
        )
        pygame.draw.line(screen, BUTTON, plot.bottomleft, plot.bottomright)

        # One point per horizontal pixel at most keeps long tournaments cheap to draw.
        step = max(1, len(self._history) // plot.width)
        sampled = list(range(0, len(self._history), step))
        if sampled[-1] != len(self._history) - 1:
            sampled.append(len(self._history) - 1)
        for column, standing in enumerate(self._standings.values()):
            points = [point(game, self._history[game][column]) for game in sampled]
            if len(points) > 1:
                pygame.draw.lines(screen, standing.color, False, points, 2)

        for index, (color, rating, lower, upper) in enumerate(fitted):
            x = plot.right + 10 + round(gutter * index / len(fitted))
            y = point(0, rating)[1]
            for start in range(plot.x, x, 8):
                pygame.draw.line(screen, color, (start, y), (min(start + 4, x), y))
            if math.isfinite(lower) and math.isfinite(upper):
                top, bottom = point(0, upper)[1], point(0, lower)[1]
                pygame.draw.line(screen, color, (x, top), (x, bottom), 2)
                for cap in (top, bottom):
                    pygame.draw.line(screen, color, (x - 3, cap), (x + 3, cap), 2)
            pygame.draw.circle(screen, color, (x, y), 3)
