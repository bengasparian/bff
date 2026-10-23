"""The weekly forecast stack (used by ff_produce.py; tested by research/bt_sites.py and tests/stacktest.py).

Within one position's group of players (those the FantasyPros experts ranked for the week), every forecast becomes a z-score
(how many sample standard deviations above the group's average): BFF's model 30%, the experts' weekly rank 10% (negated: rank 1
is best), Sleeper's projection 30%, ESPN's 30%. A player's stacked score is the weighted average of the z-scores he has. The
k-th strongest player gets the k-th highest of the players' average projected points across BFF, Sleeper and ESPN.

A site counts only when it projects at least half of the group (and 5 players). With neither site, the previously tested mix is
used: 40% model and 60% experts by z-score (population spread), mapped onto the model's own projections."""
import numpy as np

WEIGHTS = {'m': .3, 'r': .1, 's': .3, 'e': .3}   # chosen on 2020-22 (research/bt_sites.py), tested on 2023-2026
FALLBACK_EXPERTS = 0.6


def stack(model, rank, sleeper=None, espn=None, weights=WEIGHTS, fallback=FALLBACK_EXPERTS):
    """model, rank: one number per player (rank 1 = best). sleeper, espn: PPR points or None/NaN where the site has none.
    Returns (final points in the players' order, the sources used, e.g. 'm+r+s+e' or 'fallback')."""
    n = len(model)
    mv = np.asarray(model, float); ev = np.asarray(rank, float)
    def col(v): return np.full(n, np.nan) if v is None else np.array([np.nan if x is None or not (x > 0) else float(x) for x in v], float)
    V = {'m': mv, 'r': -ev, 's': col(sleeper), 'e': col(espn)}
    use = [k for k in weights if np.isfinite(V[k]).sum() >= max(5, n / 2)]
    if n < 2 or not ('s' in use or 'e' in use):
        sc = (1 - fallback) * (mv - mv.mean()) / (mv.std() or 1) - fallback * (ev - ev.mean()) / (ev.std() or 1)
        curve = np.sort(mv)[::-1]; used = 'fallback'
    else:
        num = np.zeros(n); den = np.zeros(n)
        for k in use:
            v = V[k]; ok = np.isfinite(v); sd = v[ok].std(ddof=1) or 1
            num[ok] += weights[k] * (v[ok] - v[ok].mean()) / sd; den[ok] += weights[k]
        sc = num / np.where(den > 0, den, 1)
        pts = np.array([np.mean([x for x in [mv[j]] + [V[k][j] for k in ('s', 'e') if k in use] if np.isfinite(x)]) for j in range(n)])
        curve = np.sort(pts)[::-1]; used = '+'.join(use)
    out = np.empty(n)
    out[np.argsort(-sc, kind='stable')] = curve
    return out, used
