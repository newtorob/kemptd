# SPDX-License-Identifier: GPL-3.0-or-later
"""Enable ``python -m kemptd``."""

from __future__ import annotations

from .cli import app

if __name__ == "__main__":
    app()
