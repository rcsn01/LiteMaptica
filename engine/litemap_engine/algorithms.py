from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def blur_score(gray: Sequence[Sequence[float]]) -> float:
    """Variance of a 4-neighbour Laplacian; higher means sharper."""
    if len(gray) < 3 or len(gray[0]) < 3:
        return 0.0
    values: list[float] = []
    for y in range(1, len(gray) - 1):
        for x in range(1, len(gray[y]) - 1):
            values.append(4 * gray[y][x] - gray[y - 1][x] - gray[y + 1][x] - gray[y][x - 1] - gray[y][x + 1])
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def is_hard_cut(previous_histogram: Sequence[float], current_histogram: Sequence[float], threshold: float = 0.55) -> bool:
    if len(previous_histogram) != len(current_histogram) or not previous_histogram:
        raise ValueError("histograms must have the same non-zero length")
    a = sum(previous_histogram) or 1.0
    b = sum(current_histogram) or 1.0
    distance = 0.5 * sum(abs(x / a - y / b) for x, y in zip(previous_histogram, current_histogram))
    return distance >= threshold


def confidence(occupancy: float, material: float, observations: int, disagreement: float = 0.0) -> float:
    occupancy = min(1.0, max(0.0, occupancy))
    material = min(1.0, max(0.0, material))
    support = 1.0 - math.exp(-max(0, observations) / 2.0)
    return min(1.0, max(0.0, (0.58 * occupancy + 0.42 * material) * support * (1.0 - min(1.0, max(0.0, disagreement)))))


def fit_grid_phase(planes: Iterable[float], block_scale: float) -> tuple[float, float]:
    """Circularly fit grid origin phase; returns phase and concentration confidence."""
    if block_scale <= 0:
        raise ValueError("block_scale must be positive")
    values = list(planes)
    if not values:
        raise ValueError("at least one plane is required")
    angles = [2 * math.pi * ((p / block_scale) % 1.0) for p in values]
    x = sum(math.cos(a) for a in angles) / len(angles)
    y = sum(math.sin(a) for a in angles) / len(angles)
    phase = ((math.atan2(y, x) / (2 * math.pi)) % 1.0) * block_scale
    return phase, math.hypot(x, y)


def ray_carve(origin: tuple[float, float, float], hit: tuple[float, float, float], scale: float = 1.0) -> set[tuple[int, int, int]]:
    """Conservative sampling of grid cells strictly before an observed surface hit."""
    distance = math.dist(origin, hit)
    steps = max(1, math.ceil(distance / (scale * 0.25)))
    cells: set[tuple[int, int, int]] = set()
    for i in range(steps):
        t = i / steps
        point = tuple(origin[j] + (hit[j] - origin[j]) * t for j in range(3))
        cells.add(tuple(math.floor(v / scale) for v in point))
    cells.discard(tuple(math.floor(v / scale) for v in hit))
    return cells
