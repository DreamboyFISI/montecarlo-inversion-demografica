#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lanzador de la interfaz de escritorio desde la raiz del repositorio."""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "MonteCarlo_Secuencial"))

from interfaz import InterfazMonteCarlo

if __name__ == "__main__":
    app = InterfazMonteCarlo()
    app.mainloop()

