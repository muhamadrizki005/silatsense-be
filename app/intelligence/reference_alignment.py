"""Constrained temporal matching of observable features; not semantic phase labels."""

import numpy as np

from app.intelligence.movement_features import FEATURE_NAMES
from app.intelligence.movement_training import BINS, temporal_vector

WARP_RADIUS = 6


def sequence(report, names):
    matrix = temporal_vector(report).reshape(BINS, len(FEATURE_NAMES))
    return matrix[:, [FEATURE_NAMES.index(name) for name in names]]


def align(user, reference, names):
    """Fixed endpoints and a narrow band limit matching across distant stages.

    Nulls never become joint measurements. Missing cells receive a fixed cost,
    and sufficient paired observations are required after path reconstruction.
    Angles use /180, ratios use /1 solely to balance alignment units.
    """
    user, reference = np.asarray(user, float), np.asarray(reference, float)
    expected = (BINS, len(names))
    if user.shape != expected or reference.shape != expected:
        raise ValueError("Invalid temporal matrix dimensions")
    scales = np.array([180.0 if name.endswith("_deg") else 1.0 for name in names])
    costs = np.full((BINS + 1, BINS + 1), np.inf)
    costs[0, 0] = 0
    parents = {}
    for i in range(BINS):
        for j in range(max(0, i - WARP_RADIUS), min(BINS, i + WARP_RADIUS + 1)):
            common = np.isfinite(user[i]) & np.isfinite(reference[j])
            local = (
                float(
                    np.mean(
                        np.minimum(
                            np.abs(user[i, common] - reference[j, common])
                            / scales[common],
                            1,
                        )
                    )
                )
                if common.mean() >= 0.5
                else 1.0
            )
            candidates = [
                (costs[i, j], i, j),
                (costs[i, j + 1] + 0.01, i, j + 1),
                (costs[i + 1, j] + 0.01, i + 1, j),
            ]
            cost, pi, pj = min(candidates, key=lambda item: item[0])
            costs[i + 1, j + 1] = cost + local
            parents[i + 1, j + 1] = pi, pj
    path, node = [], (BINS, BINS)
    while node != (0, 0):
        i, j = node
        if i == 0 or j == 0:
            raise ValueError("No complete temporal alignment")
        path.append((i - 1, j - 1))
        node = parents[node]
    path.reverse()
    matched, paired = np.full_like(user, np.nan), np.full_like(user, np.nan)
    reference_bins = []
    for i in range(BINS):
        js = [j for ii, j in path if ii == i]
        reference_bins.append(int(round(float(np.median(js)))))
        for k in range(len(names)):
            visible = reference[js, k]
            visible = visible[np.isfinite(visible)]
            if visible.size:
                matched[i, k] = float(np.median(visible))
                if np.isfinite(user[i, k]):
                    paired[i, k] = abs(user[i, k] - matched[i, k])
    if (
        np.isfinite(paired).mean() < 0.5
        or (np.isfinite(paired).mean(axis=1) >= 0.5).sum() < 8
    ):
        raise ValueError("Insufficient paired visibility for this movement family")
    return {
        "distance": float(costs[BINS, BINS] / len(path)),
        "referenceBins": reference_bins,
        "matched": matched,
        "deviations": paired,
    }
