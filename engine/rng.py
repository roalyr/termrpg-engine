"""
Seeded randomness that lives in the game state.

An Rng is a seed and a counter. Every draw returns its result together with the next
Rng, so the same state and the same inputs always give the same results, and a save
resumes the exact same sequence. Draws use random.Random seeded from a string, which
Python hashes with SHA-512: stable across runs, machines and versions.
"""
import random
from typing import NamedTuple, Sequence, Tuple, TypeVar, Union

T = TypeVar("T")
Number = Union[int, float]


class Rng(NamedTuple):
    seed: int
    counter: int = 0


def _draw(rng: Rng) -> Tuple[random.Random, Rng]:
    return random.Random(f"{rng.seed}:{rng.counter}"), rng._replace(counter=rng.counter + 1)


def unit(rng: Rng) -> Tuple[float, Rng]:
    """A float in [0, 1)."""
    gen, nxt = _draw(rng)
    return gen.random(), nxt


def chance(rng: Rng, p: float) -> Tuple[bool, Rng]:
    """True with probability p."""
    value, nxt = unit(rng)
    return value < p, nxt


def between(rng: Rng, low: Number, high: Number) -> Tuple[Number, Rng]:
    """A value from low to high inclusive: an integer when both bounds are integers."""
    gen, nxt = _draw(rng)
    if isinstance(low, int) and isinstance(high, int):
        return gen.randint(min(low, high), max(low, high)), nxt
    return gen.uniform(low, high), nxt


def weighted(rng: Rng, weights: Sequence[float]) -> Tuple[int, Rng]:
    """The index of one weight, chosen in proportion to the weights. Needs a positive total."""
    total = sum(weights)
    if total <= 0:
        raise ValueError("weighted() needs a positive total weight")
    value, nxt = unit(rng)
    point = value * total
    for index, weight in enumerate(weights):
        point -= weight
        if point < 0:
            return index, nxt
    return len(weights) - 1, nxt


def pick(rng: Rng, items: Sequence[T]) -> Tuple[T, Rng]:
    """One item, all equally likely."""
    if not items:
        raise ValueError("pick() needs at least one item")
    gen, nxt = _draw(rng)
    return items[gen.randrange(len(items))], nxt
