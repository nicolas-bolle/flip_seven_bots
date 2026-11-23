# Tournaments and ratings

Each tournament game selects and orders bots, constructs a fresh instance for
each seat, and plays a complete game to the target score. State can persist
between rounds of that game, but not between games.

The tournament seed controls seating, decks and each bot's seed. With the same
configuration, deterministic seeded factories and runtime, changing `jobs`
does not change game records: games are rated in scheduled order, not
completion order. An omitted seed is random and cannot be reproduced from the
saved settings. A bot using an external random source must seed that source
itself. Registered bot instances passed to the Python API provide configuration
only; their existing random state is not used.

Parallel work uses processes. Only a bounded number of games are in flight.
Stopping the window stops scheduling new work and waits for in-flight work to
finish; only completed records delivered before stopping appear in the result.
Errors from workers are surfaced rather than silently retried.

Results contain an order-independent Bradley–Terry rating with a confidence
interval and a game-by-game online Elo. Ties count as shared wins. Ratings
assume strength is independent of opponents and table size, so compare runs
with the same table size. For the calculation and its limitations, see
[How ratings work](reference.md#how-ratings-work).
