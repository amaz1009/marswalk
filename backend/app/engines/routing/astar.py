"""A* shortest-path search on analysis grid.

Implements the deterministic A* pathfinding algorithm with 8-connectivity,
strict corner-cutting prohibition, admissible octile heuristic, and
deterministic tie-breaking per MARSWALK SCIENCE_AND_SAFETY_SPEC.md
sections 7.1, 7.4, and 7.5.
"""

import heapq
import math
from dataclasses import dataclass

import numpy as np

from app.engines.eva.speed import compute_step_time, walking_speed
from app.engines.hazards.grid import HazardState

# Fixed 8-neighbour direction sequence: N, NE, E, SE, S, SW, W, NW (section 7.1)
# (dr, dc, is_diagonal, (adj1_dr, adj1_dc), (adj2_dr, adj2_dc))
NEIGHBOUR_OFFSETS = [
    (-1, 0, False, (0, 0), (0, 0)),  # N
    (-1, 1, True, (-1, 0), (0, 1)),  # NE: adjacent orthogonal are N and E
    (0, 1, False, (0, 0), (0, 0)),  # E
    (1, 1, True, (1, 0), (0, 1)),  # SE: adjacent orthogonal are S and E
    (1, 0, False, (0, 0), (0, 0)),  # S
    (1, -1, True, (1, 0), (0, -1)),  # SW: adjacent orthogonal are S and W
    (0, -1, False, (0, 0), (0, 0)),  # W
    (-1, -1, True, (-1, 0), (0, -1)),  # NW: adjacent orthogonal are N and W
]

SQRT2 = math.sqrt(2.0)
SQRT2_MINUS_ONE = SQRT2 - 1.0


@dataclass(frozen=True)
class AStarResult:
    """Result of an A* pathfinding search.

    Attributes:
        success: True if an optimal path from start to goal was found.
        path: List of (row, col) coordinates along the path from start to goal.
        total_cost: Cumulative weighted objective cost along the path.
        horizontal_distance_m: Total 2D planar path distance in metres.
        surface_distance_m: Total 3D surface path distance in metres.
        ascent_m: Cumulative elevation gain along the path in metres.
        descent_m: Cumulative elevation loss along the path in metres.
        walk_time_s: Total walking time along the path in seconds (without margin).
        visited_nodes: Number of nodes expanded from the open set.
    """

    success: bool
    path: list[tuple[int, int]]
    total_cost: float
    horizontal_distance_m: float
    surface_distance_m: float
    ascent_m: float
    descent_m: float
    walk_time_s: float
    visited_nodes: int


def octile_heuristic(
    r1: int,
    c1: int,
    r2: int,
    c2: int,
    cell_size_m: float,
    w_sci: float,
    base_speed_kmh: float = 2.7,
) -> float:
    """Compute admissible and consistent octile distance heuristic (section 7.4).

    Formula:
        D_octile = cell_size_m * (max(|dr|, |dc|) + (sqrt(2) - 1) * min(|dr|, |dc|))
        v_max = base_speed_kmh * exp(0.175)
        h = D_octile * (1 - w_sci) / (v_max / 3.6)

    Args:
        r1, c1: Current cell row and column.
        r2, c2: Goal cell row and column.
        cell_size_m: Cell size in metres.
        w_sci: Science weight factor in [0.0, 0.5].
        base_speed_kmh: Base walking speed in km/h.

    Returns:
        Admissible lower bound on remaining cost.
    """
    dr = abs(r1 - r2)
    dc = abs(c1 - c2)
    min_d = min(dr, dc)
    max_d = max(dr, dc)
    d_octile = cell_size_m * (max_d + SQRT2_MINUS_ONE * min_d)

    # Maximum speed occurs at slope S = -0.05: v_max = base_speed_kmh * exp(0.175)
    v_max_kmh = walking_speed(-0.05, base_speed_kmh=base_speed_kmh)
    v_max_ms = v_max_kmh / 3.6

    min_factor = 1.0 - w_sci
    return float(d_octile * min_factor / v_max_ms)


def _step_time_scalar(dz: float, dh: float, v0_ms: float) -> float:
    """Fast scalar traversal time calculation for adjacent cells."""
    grad = dz / dh
    exponent = -3.5 * (abs(grad + 0.05) - 0.05)
    speed_ms = v0_ms * math.exp(exponent)
    return math.sqrt(dh * dh + dz * dz) / speed_ms


def run_astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    elevation: np.ndarray,
    hazard_states: np.ndarray,
    cell_cost_factors: np.ndarray,
    cell_size_m: float,
    base_speed_kmh: float = 2.7,
    w_sci: float = 0.0,
    use_heuristic: bool = True,
) -> AStarResult:
    """Execute A* pathfinding search between two grid cells.

    Args:
        start: (row, col) coordinates of start cell.
        goal: (row, col) coordinates of goal cell.
        elevation: 2D float32/float64 array of elevations in metres.
        hazard_states: 2D array of HazardState values (0 = PASSABLE).
        cell_cost_factors: 2D float64 array of precomputed static cost multipliers.
        cell_size_m: Horizontal grid resolution in metres.
        base_speed_kmh: Nominal flat-terrain walking speed in km/h.
        w_sci: Science attraction weight for heuristic scaling.
        use_heuristic: If True, uses octile heuristic; if False, runs Dijkstra (h = 0).

    Returns:
        AStarResult dataclass.
    """
    rows, cols = elevation.shape
    start_r, start_c = start
    goal_r, goal_c = goal

    # Guard bounds and passability of endpoints
    if not (0 <= start_r < rows and 0 <= start_c < cols):
        return AStarResult(False, [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
    if not (0 <= goal_r < rows and 0 <= goal_c < cols):
        return AStarResult(False, [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    if hazard_states[start_r, start_c] != HazardState.PASSABLE:
        return AStarResult(False, [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
    if hazard_states[goal_r, goal_c] != HazardState.PASSABLE:
        return AStarResult(False, [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    # Trivial case: start is goal
    if start == goal:
        return AStarResult(
            success=True,
            path=[start],
            total_cost=0.0,
            horizontal_distance_m=0.0,
            surface_distance_m=0.0,
            ascent_m=0.0,
            descent_m=0.0,
            walk_time_s=0.0,
            visited_nodes=1,
        )

    # Verify no NaN on start/goal elevation
    start_z = float(elevation[start_r, start_c])
    goal_z = float(elevation[goal_r, goal_c])
    if math.isnan(start_z) or math.isnan(goal_z):
        raise ValueError("Passable cell has NaN elevation; violates data validity rule")

    num_cells = rows * cols
    start_idx = start_r * cols + start_c
    goal_idx = goal_r * cols + goal_c

    # Flat views for cache-friendly fast indexing
    elev_flat = elevation.ravel()
    haz_flat = hazard_states.ravel()
    cost_flat = cell_cost_factors.ravel()

    # Tracking arrays
    g_score = np.full(num_cells, np.inf, dtype=np.float64)
    came_from = np.full(num_cells, -1, dtype=np.int32)
    closed = np.zeros(num_cells, dtype=bool)

    v0_ms = base_speed_kmh / 3.6
    v_max_ms = (base_speed_kmh * math.exp(0.175)) / 3.6
    h_scale = (cell_size_m * (1.0 - w_sci)) / v_max_ms if use_heuristic else 0.0

    dr_start = abs(start_r - goal_r)
    dc_start = abs(start_c - goal_c)
    h_start = (max(dr_start, dc_start) + SQRT2_MINUS_ONE * min(dr_start, dc_start)) * h_scale

    g_score[start_idx] = 0.0

    # Priority queue key: (f, h, insertion_counter, u_idx) (section 7.5)
    counter = 0
    open_heap: list[tuple[float, float, int, int]] = []
    heapq.heappush(open_heap, (h_start, h_start, counter, start_idx))

    ortho_dist = float(cell_size_m)
    diag_dist = float(cell_size_m * SQRT2)
    ortho_time = ortho_dist / v0_ms
    diag_time = diag_dist / v0_ms
    visited_nodes = 0
    found = False

    while open_heap:
        f_val, h_val, _, u_idx = heapq.heappop(open_heap)

        if closed[u_idx]:
            continue
        closed[u_idx] = True
        visited_nodes += 1

        if u_idx == goal_idx:
            found = True
            break

        ur, uc = divmod(u_idx, cols)
        u_z = float(elev_flat[u_idx])
        if math.isnan(u_z):
            raise ValueError(f"Encountered NaN elevation at cell ({ur}, {uc})")

        current_g = g_score[u_idx]

        is_interior = (0 < ur < rows - 1) and (0 < uc < cols - 1)

        # Expand neighbours in fixed order: N, NE, E, SE, S, SW, W, NW
        for dr, dc, is_diagonal, (adj1_dr, adj1_dc), (adj2_dr, adj2_dc) in NEIGHBOUR_OFFSETS:
            nr = ur + dr
            nc = uc + dc

            if not is_interior:
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue

            v_idx = nr * cols + nc
            if closed[v_idx]:
                continue

            # Passability check for target cell
            if haz_flat[v_idx] != HazardState.PASSABLE:
                continue

            # Strict corner-cutting prohibition for diagonal moves (section 7.1)
            if is_diagonal:
                o1_idx = (ur + adj1_dr) * cols + (uc + adj1_dc)
                o2_idx = (ur + adj2_dr) * cols + (uc + adj2_dc)
                if not is_interior:
                    o1_r, o1_c = ur + adj1_dr, uc + adj1_dc
                    o2_r, o2_c = ur + adj2_dr, uc + adj2_dc
                    if not (0 <= o1_r < rows and 0 <= o1_c < cols):
                        continue
                    if not (0 <= o2_r < rows and 0 <= o2_c < cols):
                        continue
                if haz_flat[o1_idx] != HazardState.PASSABLE:
                    continue
                if haz_flat[o2_idx] != HazardState.PASSABLE:
                    continue

            v_z = float(elev_flat[v_idx])
            if math.isnan(v_z):
                raise ValueError(f"Encountered NaN elevation at cell ({nr}, {nc})")

            dz = v_z - u_z
            dh = diag_dist if is_diagonal else ortho_dist

            step_time = (
                (diag_time if is_diagonal else ortho_time)
                if dz == 0.0
                else _step_time_scalar(dz, dh, v0_ms)
            )
            step_cost = step_time * float(cost_flat[v_idx])
            tentative_g = current_g + step_cost

            if tentative_g < g_score[v_idx]:
                g_score[v_idx] = tentative_g
                came_from[v_idx] = u_idx
                dr_goal = abs(nr - goal_r)
                dc_goal = abs(nc - goal_c)
                h_next = (
                    (max(dr_goal, dc_goal) + SQRT2_MINUS_ONE * min(dr_goal, dc_goal)) * h_scale
                    if use_heuristic
                    else 0.0
                )
                counter += 1
                heapq.heappush(open_heap, (tentative_g + h_next, h_next, counter, v_idx))

    if not found:
        return AStarResult(
            success=False,
            path=[],
            total_cost=0.0,
            horizontal_distance_m=0.0,
            surface_distance_m=0.0,
            ascent_m=0.0,
            descent_m=0.0,
            walk_time_s=0.0,
            visited_nodes=visited_nodes,
        )

    # Backtrack path from goal to start
    path_indices: list[int] = []
    curr = goal_idx
    while curr != -1:
        path_indices.append(curr)
        curr = int(came_from[curr])
    path_indices.reverse()

    path_coords = [(idx // cols, idx % cols) for idx in path_indices]

    # Compute path statistics along reconstructed segments
    total_cost = float(g_score[goal_idx])
    total_h_dist = 0.0
    total_s_dist = 0.0
    total_ascent = 0.0
    total_descent = 0.0
    total_walk_time = 0.0

    for i in range(len(path_coords) - 1):
        r_a, c_a = path_coords[i]
        r_b, c_b = path_coords[i + 1]

        dr = abs(r_b - r_a)
        dc = abs(c_b - c_a)
        is_diag = (dr == 1) and (dc == 1)
        dh = diag_dist if is_diag else ortho_dist

        z_a = float(elev_flat[r_a * cols + c_a])
        z_b = float(elev_flat[r_b * cols + c_b])
        dz = z_b - z_a

        ds = math.sqrt(dh * dh + dz * dz)
        st = compute_step_time(dz, dh, base_speed_kmh=base_speed_kmh)

        total_h_dist += dh
        total_s_dist += ds
        total_walk_time += st
        if dz > 0.0:
            total_ascent += dz
        else:
            total_descent += abs(dz)

    return AStarResult(
        success=True,
        path=path_coords,
        total_cost=total_cost,
        horizontal_distance_m=total_h_dist,
        surface_distance_m=total_s_dist,
        ascent_m=total_ascent,
        descent_m=total_descent,
        walk_time_s=total_walk_time,
        visited_nodes=visited_nodes,
    )
