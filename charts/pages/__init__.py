"""charts.pages — single import surface for the router."""

from __future__ import annotations

from ._context import PageContext
from . import contents as _contents
from . import liquidity_overview as _liquidity
from . import policy as _policy
from . import policy_futures as _policy_futures
from . import decomposition as _decomposition
from . import regimes as _regimes
from . import global_rates as _global_rates
from . import country_boards as _country_boards
from . import cross_asset as _cross_asset
from . import market_linkage as _market_linkage
from . import sector_rotation as _sector_rotation
from . import sector_contribution as _sector_contribution
from . import index_breadth as _index_breadth
from . import earnings_valuation as _earnings_valuation
from . import fx_rate_diff as _fx_rate_diff
from . import data_quality as _data_quality
from . import scoring as _scoring
from . import scoring_backtest as _scoring_backtest
from . import model_roadmap as _model_roadmap


RENDERERS = {
    "contents":       _contents.render,
    "liquidity":      _liquidity.render,
    "policy":         _policy.render,
    "policy_futures": _policy_futures.render,
    "decomposition":  _decomposition.render,
    "regimes":        _regimes.render,
    "global_rates":   _global_rates.render,
    "country_boards": _country_boards.render,
    "cross_asset":    _cross_asset.render,
    "market_linkage": _market_linkage.render,
    "fx_rate_diff":   _fx_rate_diff.render,
    "sector_rotation": _sector_rotation.render,
    "sector_contribution": _sector_contribution.render,
    "index_breadth": _index_breadth.render,
    "earnings_valuation": _earnings_valuation.render,
    "data_quality":   _data_quality.render,
    "scoring":        _scoring.render,
    "scoring_backtest": _scoring_backtest.render,
    "model_roadmap":  _model_roadmap.render,
}


def render_page(page_id: str, ctx: PageContext) -> None:
    if page_id not in RENDERERS:
        raise KeyError(f"Unknown page id: {page_id}")
    RENDERERS[page_id](ctx)
