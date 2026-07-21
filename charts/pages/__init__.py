"""charts.pages — single import surface for the router."""

from __future__ import annotations

from ._context import PageContext
from . import contents as _contents
from . import liquidity_overview as _liquidity
from . import policy as _policy
from . import decomposition as _decomposition
from . import rates_pca as _rates_pca
from . import regimes as _regimes
from . import global_rates as _global_rates
from . import cross_asset as _cross_asset
from . import market_linkage as _market_linkage
from . import fx as _fx
from . import data_quality as _data_quality
from . import scoring as _scoring


RENDERERS = {
    "contents":       _contents.render,
    "liquidity":      _liquidity.render,
    "policy":         _policy.render,
    "decomposition":  _decomposition.render,
    "rates_pca":      _rates_pca.render,
    "regimes":        _regimes.render,
    "global_rates":   _global_rates.render,
    "cross_asset":    _cross_asset.render,
    "market_linkage": _market_linkage.render,
    "fx":             _fx.render,
    "data_quality":   _data_quality.render,
    "scoring":        _scoring.render,
}


def render_page(page_id: str, ctx: PageContext) -> None:
    if page_id not in RENDERERS:
        raise KeyError(f"Unknown page id: {page_id}")
    RENDERERS[page_id](ctx)
