"""Residual roughness computation engine.

Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.3 and Amendment A-2 (D-013):
- Residual RMS roughness separates small-scale relief from overall slope.
- Fits a plane z = alpha * x + beta * y + gamma by least squares to kxk window (k=3).
- Roughness is the root-mean-square of the residuals in metres.
- If any cell in the window is NaN, roughness is NaN.
- Edge cells have NaN roughness.
- Uses per-row ground spacing dx_ground and dy per Amendment A-2.
"""

import numpy as np


def compute_residual_roughness(
    elevation: np.ndarray,
    dx_ground: np.ndarray,
    dy: float,
    k: int = 3,
    chunk_size: int = 2000,
) -> np.ndarray:
    """Compute residual RMS roughness in metres with a kxk window (default k=3).

    Implements docs/SCIENCE_AND_SAFETY_SPEC.md section 4.3 and Amendment A-2:
    1. For each cell, take 3x3 window centred on it.
    2. Fit plane z = alpha * x + beta * y + gamma by least squares.
    3. Roughness is root-mean-square of residuals: RMS = sqrt(mean(residuals^2)).
    4. If any cell in the window is NaN, roughness is NaN.
    5. Edge cells are NaN.

    For k=3, coordinates x in {-dx, 0, dx} and y in {-dy, 0, dy} are symmetric around 0,
    so sum(x) = 0, sum(y) = 0, sum(xy) = 0.
    The normal equations decouple analytically:
        gamma = mean(z)
        alpha = sum(x * z) / (6 * dx^2) = ((c + f + i) - (a + d + g)) / (6 * dx)
        beta  = sum(y * z) / (6 * dy^2) = ((g + h + i) - (a + b + c)) / (6 * dy)
        SS_res = sum(z^2) - 9 * gamma^2 - 6 * dx^2 * alpha^2 - 6 * dy^2 * beta^2
        RMS = sqrt(max(0, SS_res / 9))

    Args:
        elevation: 2D float32 numpy array of elevations in metres.
        dx_ground: 1D array of per-row dx ground spacings of length elevation.shape[0].
        dy: Scalar dy ground spacing in metres.
        k: Window size (default 3; currently k=3 is supported analytically).
        chunk_size: Number of interior rows to process per chunk.

    Returns:
        2D float32 numpy array of residual roughness values in metres, with NaN for
        invalid and edge cells.
    """
    if k != 3:
        raise NotImplementedError(
            f"Window size k={k} not implemented; default k=3 required by spec section 4.3."
        )

    height, width = elevation.shape
    roughness = np.full((height, width), np.nan, dtype=np.float32)

    if height < 3 or width < 3:
        return roughness

    # dy divisor is constant: 6 * dy
    denom_y = 6.0 * dy

    # Process interior rows in chunks
    for r_start in range(1, height - 1, chunk_size):
        r_end = min(r_start + chunk_size, height - 1)

        # Convert chunk to float64 for numerically stable residual calculation
        z_block = elevation[r_start - 1 : r_end + 1, :].astype(np.float64)
        dx_sub = dx_ground[r_start:r_end, None]
        denom_x = 6.0 * dx_sub

        # Center elevation relative to central cell e to eliminate constant elevation
        # offsets (e.g. -4000 m on Mars) and prevent float32 catastrophic cancellation
        e_center = z_block[1:-1, 1:-1]
        a = z_block[:-2, :-2] - e_center
        b = z_block[:-2, 1:-1] - e_center
        c = z_block[:-2, 2:] - e_center
        d = z_block[1:-1, :-2] - e_center
        e = np.zeros_like(e_center)
        f = z_block[1:-1, 2:] - e_center
        g = z_block[2:, :-2] - e_center
        h = z_block[2:, 1:-1] - e_center
        i = z_block[2:, 2:] - e_center

        # Valid mask: all 9 cells must be non-NaN
        valid_9 = (
            ~np.isnan(a)
            & ~np.isnan(b)
            & ~np.isnan(c)
            & ~np.isnan(d)
            & ~np.isnan(e_center)
            & ~np.isnan(f)
            & ~np.isnan(g)
            & ~np.isnan(h)
            & ~np.isnan(i)
        )

        # Mean of centered elevation
        sum_z = a + b + c + d + e + f + g + h + i
        gamma = sum_z / 9.0

        # Slopes alpha and beta of best-fit plane
        alpha = ((c + f + i) - (a + d + g)) / denom_x
        beta = ((g + h + i) - (a + b + c)) / denom_y

        # Direct residuals: r_p = z'_p - (gamma + alpha*x_p + beta*y_p)
        # Guarantees non-negative sum of squares and exact zero on perfect planes
        r_a = a - (gamma - alpha * dx_sub - beta * dy)
        r_b = b - (gamma - beta * dy)
        r_c = c - (gamma + alpha * dx_sub - beta * dy)
        r_d = d - (gamma - alpha * dx_sub)
        r_e = e - gamma
        r_f = f - (gamma + alpha * dx_sub)
        r_g = g - (gamma - alpha * dx_sub + beta * dy)
        r_h = h - (gamma + beta * dy)
        r_i = i - (gamma + alpha * dx_sub + beta * dy)

        ss_res = r_a**2 + r_b**2 + r_c**2 + r_d**2 + r_e**2 + r_f**2 + r_g**2 + r_h**2 + r_i**2
        chunk_rms = np.sqrt(ss_res / 9.0)

        # Enforce NaN where any of 9 cells is NaN
        chunk_rms = np.where(valid_9, chunk_rms, np.nan)

        roughness[r_start:r_end, 1:-1] = chunk_rms.astype(np.float32)

    return roughness
