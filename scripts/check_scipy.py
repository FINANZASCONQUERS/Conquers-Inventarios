"""Quick check for scipy.interpolate.CubicSpline availability."""
import sys
try:
    from scipy.interpolate import CubicSpline
    import numpy as np

    x = [0.0, 1.0, 2.0]
    y = [0.0, 1.0, 0.0]
    cs = CubicSpline(x, y)
    xi = 1.5
    yi = cs(xi)
    print("CubicSpline OK", yi)
    sys.exit(0)
except Exception as e:
    print("CubicSpline import or execution failed:", repr(e))
    sys.exit(2)
