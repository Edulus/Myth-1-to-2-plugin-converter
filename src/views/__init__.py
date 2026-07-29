"""Views over a `src.plan.Plan`.

A view renders a plan. It never decides anything and never writes game data --
that separation is the point (see `src/plan.py`).

    text  a terminal report
    html  an interactive page: shows the plan, collects decisions, and emits
          the decisions file that feeds back into `convert --decisions`
"""

from . import html, text  # noqa: F401
