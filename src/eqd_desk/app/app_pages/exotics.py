"""Exotics (Phase 3): where vanilla intuition stops being enough.

Four instruments, one sub-tab each (React ``ExoticsLab.tsx``): a single-barrier option (the
gamma blow-up at the barrier), a cash-or-nothing digital (pin risk and its call-spread
replication), a Phoenix autocallable (path-dependence, priced by Monte Carlo) and a variance
swap (the 1/K² strip and the convexity premium over ATM). Each view is a three-column
terminal: controls and readout, the characteristic chart, and the Learn panel.

The views (widgets, layout, caching) live in :mod:`eqd_desk.app.ui.exotics_views`; their
pure halves in :mod:`eqd_desk.app.ui.exotics_curves` (the numbers),
:mod:`eqd_desk.app.ui.exotics_charts` (the charts) and :mod:`eqd_desk.app.ui.exotics_display`
(the readout rows and notes). Only the selected sub-tab is computed.
"""

from __future__ import annotations

from eqd_desk.app.ui import state
from eqd_desk.app.ui.exotics_views import VIEWS, exotic_picker

snap = state.snapshot()
kind = exotic_picker()
VIEWS[kind](snap)
