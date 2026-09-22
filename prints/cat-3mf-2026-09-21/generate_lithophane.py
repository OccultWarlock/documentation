#!/usr/bin/env python3
"""Build printable lithophanes from the Bengal cat photo.

Brightness becomes thickness: bright fur and the green eyes are thin
(they glow when backlit); dark fur is thicker.

Two shapes:

- plate: rectangular frame, black background kept, printed standing up
- silhouette: background cut away so the outline is the cat, printed flat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageFilter

# Plate is sampled at the nozzle line width so features stay printable.
PITCH_MM = 0.4
IMAGE_ROWS = 300  # 120.0 mm of picture
SIDE_COLS = 4  # 1.6 mm opaque frame, left and right
TOP_ROWS = 8  # 3.2 mm opaque frame above the picture
BASE_ROWS = 8  # 3.2 mm full-thickness foot
T_MIN_MM = 1.0  # brightest pixel
T_MAX_MM = 3.4  # darkest pixel / frame / foot
# Back face may grow this steeply as Z increases (degrees from vertical).
MAX_OVERHANG_DEG = 50.0
TONE_GAMMA = 0.8
# Silhouette long side. Pitch stays near one nozzle width.
SILHOUETTE_LONG_MM = 130.0
SILHOUETTE_CELLS = int(round(SILHOUETTE_LONG_MM / PITCH_MM))


def luminance_over_black(path: Path) -> np.ndarray:
    """Composite the photo onto black and return Rec.709 luminance, 0–255."""
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3:4] / 255.0
    comp = rgb * alpha
    lum = 0.2126 * comp[..., 0] + 0.7152 * comp[..., 1] + 0.0722 * comp[..., 2]
    return lum


def resize_luminance(lum: np.ndarray, rows: int, cols: int) -> np.ndarray:
    image = Image.fromarray(lum.astype(np.float32), mode="F")
    image = image.resize((cols, rows), Image.Resampling.LANCZOS)
    out = np.asarray(image, dtype=np.float32)
    if float(out.max()) > 1.5:
        out = out / 255.0
    return np.clip(out, 0.0, 1.0)


def tone_to_thickness(lum: np.ndarray) -> np.ndarray:
    """Map 0–1 luminance to millimeters. Bright → thin, dark → thick."""
    x = np.clip((lum - 0.015) / 0.985, 0.0, 1.0)
    x = np.power(x, TONE_GAMMA)
    # Light blur kills single-sample spikes without erasing the spots.
    blurred = Image.fromarray(np.clip(x * 255.0, 0, 255).astype(np.uint8), mode="L")
    blurred = blurred.filter(ImageFilter.GaussianBlur(radius=0.7))
    x = np.asarray(blurred, dtype=np.float32) / 255.0
    thickness = T_MAX_MM - x * (T_MAX_MM - T_MIN_MM)
    return np.clip(thickness, T_MIN_MM, T_MAX_MM)


def limit_upward_growth(thickness: np.ndarray, max_dt: float) -> np.ndarray:
    """Keep the back face from overhanging as the print grows in +Z.

    Row 0 is the top of the plate. Printing starts at the last row, so a
    row may not be much thicker than the row below it.
    """
    limited = np.array(thickness, dtype=np.float64, copy=True)
    for row in range(limited.shape[0] - 2, -1, -1):
        limited[row] = np.minimum(limited[row], limited[row + 1] + max_dt)
    return np.clip(limited, T_MIN_MM, T_MAX_MM)


def compose_thickness(lum_full: np.ndarray) -> np.ndarray:
    aspect = lum_full.shape[1] / lum_full.shape[0]
    image_cols = int(round(IMAGE_ROWS * aspect))
    resized = resize_luminance(lum_full, IMAGE_ROWS, image_cols)
    picture = tone_to_thickness(resized)

    rows = IMAGE_ROWS + TOP_ROWS + BASE_ROWS
    cols = image_cols + 2 * SIDE_COLS
    plate = np.full((rows, cols), T_MAX_MM, dtype=np.float64)
    plate[TOP_ROWS : TOP_ROWS + IMAGE_ROWS, SIDE_COLS : SIDE_COLS + image_cols] = picture

    max_dt = float(np.tan(np.deg2rad(MAX_OVERHANG_DEG)) * PITCH_MM)
    return limit_upward_growth(plate, max_dt)


def _grid_faces(rows: int, cols: int, layer: int, back: bool) -> np.ndarray:
    rr, cc = np.meshgrid(
        np.arange(rows - 1, dtype=np.int64),
        np.arange(cols - 1, dtype=np.int64),
        indexing="ij",
    )
    base = layer * rows * cols
    v00 = base + rr * cols + cc
    v01 = v00 + 1
    v10 = v00 + cols
    v11 = v10 + 1
    if back:
        # Outward normal is +X (textured back).
        t1 = np.stack([v00, v01, v10], axis=-1)
        t2 = np.stack([v01, v11, v10], axis=-1)
    else:
        # Outward normal is -X (flat front).
        t1 = np.stack([v00, v10, v01], axis=-1)
        t2 = np.stack([v01, v10, v11], axis=-1)
    return np.concatenate([t1.reshape(-1, 3), t2.reshape(-1, 3)], axis=0)


def _wall_faces(rows: int, cols: int) -> np.ndarray:
    """Close the four edges. Windings match the front/back caps."""
    front = 0
    back = rows * cols
    faces = []

    # Bottom, row = rows-1, outward -Z.
    r = rows - 1
    c = np.arange(cols - 1, dtype=np.int64)
    f_c = front + r * cols + c
    f_c1 = f_c + 1
    b_c = back + r * cols + c
    b_c1 = b_c + 1
    faces.append(np.stack([f_c1, f_c, b_c], axis=-1))
    faces.append(np.stack([f_c1, b_c, b_c1], axis=-1))

    # Top, row = 0, outward +Z.
    f_c = front + c
    f_c1 = f_c + 1
    b_c = back + c
    b_c1 = b_c + 1
    faces.append(np.stack([f_c, f_c1, b_c1], axis=-1))
    faces.append(np.stack([f_c, b_c1, b_c], axis=-1))

    # Image-left edge, col = 0, outward +Y.
    r = np.arange(rows - 1, dtype=np.int64)
    f_r = front + r * cols
    f_r1 = front + (r + 1) * cols
    b_r = back + r * cols
    b_r1 = back + (r + 1) * cols
    faces.append(np.stack([f_r1, f_r, b_r], axis=-1))
    faces.append(np.stack([f_r1, b_r, b_r1], axis=-1))

    # Image-right edge, col = cols-1, outward -Y.
    f_r = front + r * cols + (cols - 1)
    f_r1 = front + (r + 1) * cols + (cols - 1)
    b_r = back + r * cols + (cols - 1)
    b_r1 = back + (r + 1) * cols + (cols - 1)
    faces.append(np.stack([f_r, f_r1, b_r1], axis=-1))
    faces.append(np.stack([f_r, b_r1, b_r], axis=-1))

    return np.concatenate(faces, axis=0)


def build_mesh(thickness: np.ndarray) -> trimesh.Trimesh:
    rows, cols = thickness.shape
    z_rows = (rows - 1 - np.arange(rows, dtype=np.float64)) * PITCH_MM
    # Column 0 is image-left. From the flat front that is the viewer's left,
    # which is +Y when looking in the +X direction.
    y_cols = (cols - 1 - np.arange(cols, dtype=np.float64)) * PITCH_MM
    y_grid, z_grid = np.meshgrid(y_cols, z_rows)

    front_xyz = np.stack(
        [np.zeros((rows, cols), dtype=np.float64), y_grid, z_grid], axis=-1
    )
    back_xyz = np.stack(
        [np.asarray(thickness, dtype=np.float64), y_grid, z_grid], axis=-1
    )
    vertices = np.concatenate(
        [front_xyz.reshape(-1, 3), back_xyz.reshape(-1, 3)], axis=0
    )
    vertices = np.round(vertices, decimals=4)

    faces = np.concatenate(
        [
            _grid_faces(rows, cols, layer=0, back=False),
            _grid_faces(rows, cols, layer=1, back=True),
            _wall_faces(rows, cols),
        ],
        axis=0,
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    return mesh


def assert_printable(mesh: trimesh.Trimesh) -> None:
    if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise SystemExit("mesh is empty")
    if not mesh.is_watertight:
        raise SystemExit("mesh is not watertight")
    if not mesh.is_winding_consistent:
        raise SystemExit("mesh winding is inconsistent")
    if mesh.euler_number != 2:
        raise SystemExit(f"expected a single solid (euler 2), got {mesh.euler_number}")
    if mesh.volume <= 0:
        raise SystemExit(f"non-positive volume: {mesh.volume}")
    if np.any(mesh.area_faces <= 1e-8):
        raise SystemExit("mesh has degenerate faces")

    unique_edges, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    if unique_edges.shape[0] == 0 or not np.all(counts == 2):
        bad = int(np.count_nonzero(counts != 2))
        raise SystemExit(f"non-manifold edges: {bad}")

    extents = mesh.extents
    thickness, width, height = (float(v) for v in extents)
    if not (2.0 <= thickness <= 4.5):
        raise SystemExit(f"thickness extent {thickness:.2f} mm is outside 2–4 mm class")
    long_side = max(width, height)
    if not (100.0 <= long_side <= 150.0):
        raise SystemExit(f"long side {long_side:.2f} mm is outside 100–150 mm")
    if float(mesh.bounds[0, 2]) < -1e-4:
        raise SystemExit("model extends below the bed")
    print(
        f"mesh ok  vertices={len(mesh.vertices)} faces={len(mesh.faces)} "
        f"volume={mesh.volume:.1f} mm^3  "
        f"size={width:.2f} x {height:.2f} x {thickness:.2f} mm (Y x Z x X)"
    )


def write_preview(thickness: np.ndarray, path: Path) -> None:
    """Front view: thin (bright) is white, thick (dark) is black."""
    shown = (T_MAX_MM - thickness) / (T_MAX_MM - T_MIN_MM)
    # Flip vertically for image files (row 0 is the top of the plate).
    image = Image.fromarray(np.clip(shown * 255.0, 0, 255).astype(np.uint8), mode="L")
    image.save(path)


def _four_connected():
    from scipy import ndimage

    return ndimage.generate_binary_structure(2, 1)


def _tone_array(lum_0_255: np.ndarray) -> np.ndarray:
    """lum is 0–255. Outside the cat, pass zeros so the rim stays a little thicker."""
    return tone_to_thickness(np.clip(lum_0_255, 0.0, 255.0) / 255.0)


def prepare_silhouette(path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Crop to the cat, drop the background, and return thickness, mask, pitch."""
    from scipy import ndimage

    rgba = np.asarray(Image.open(path).convert("RGBA"))
    alpha = rgba[..., 3]
    ys, xs = np.where(alpha >= 128)
    if len(ys) == 0:
        raise SystemExit("no opaque cat pixels in the source image")
    crop = rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    long_px = max(crop.shape[0], crop.shape[1])
    scale = SILHOUETTE_CELLS / long_px
    rows = max(1, int(round(crop.shape[0] * scale)))
    cols = max(1, int(round(crop.shape[1] * scale)))
    resized = np.asarray(
        Image.fromarray(crop, mode="RGBA").resize((cols, rows), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    rgb = resized[..., :3]
    alpha_r = resized[..., 3:4] / 255.0
    comp = rgb * alpha_r
    lum = 0.2126 * comp[..., 0] + 0.7152 * comp[..., 1] + 0.0722 * comp[..., 2]
    mask = resized[..., 3] >= 128.0
    thickness = _tone_array(lum)

    struct = _four_connected()
    mask = ndimage.binary_opening(mask, structure=struct)
    labels, count = ndimage.label(mask, structure=struct)
    if count == 0:
        raise SystemExit("silhouette opened away to nothing")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    mask = labels == int(np.argmax(sizes))

    mask = _fill_small_holes(mask, max_cells=25)
    added = mask.copy()
    mask = _bridge_diagonal_contacts(mask)
    thickness = _nearest_thickness(thickness, added, mask)

    ys, xs = np.where(mask)
    mask = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    thickness = thickness[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    thickness = np.where(mask, np.clip(thickness, T_MIN_MM, T_MAX_MM), 0.0)
    pitch = SILHOUETTE_LONG_MM / max(mask.shape)
    return thickness, mask, float(pitch)


def _fill_small_holes(mask: np.ndarray, max_cells: int) -> np.ndarray:
    from scipy import ndimage

    holes, count = ndimage.label(~mask, structure=_four_connected())
    if count == 0:
        return mask
    border = np.unique(
        np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]])
    )
    sizes = np.bincount(holes.ravel())
    drop = np.zeros(count + 1, dtype=bool)
    drop[border] = False
    for label in range(1, count + 1):
        if label in border:
            continue
        if sizes[label] <= max_cells:
            drop[label] = True
    return mask | drop[holes]


def _bridge_diagonal_contacts(mask: np.ndarray) -> np.ndarray:
    """Fill one cell of a diagonal-only touch so corners are not pinched."""
    bridged = np.array(mask, dtype=bool, copy=True)
    for _ in range(bridged.size):
        top_left = bridged[:-1, :-1]
        top_right = bridged[:-1, 1:]
        bot_left = bridged[1:, :-1]
        bot_right = bridged[1:, 1:]
        main = top_left & bot_right & ~top_right & ~bot_left
        anti = top_right & bot_left & ~top_left & ~bot_right
        if not main.any() and not anti.any():
            break
        bridged[:-1, 1:] |= main
        bridged[:-1, :-1] |= anti
    return bridged


def _nearest_thickness(
    thickness: np.ndarray, source: np.ndarray, dest: np.ndarray
) -> np.ndarray:
    """Copy thickness onto cells the silhouette cleanup added."""
    from scipy import ndimage

    added = dest & ~source
    if not added.any():
        return thickness
    indices = ndimage.distance_transform_edt(~source, return_distances=False, return_indices=True)
    out = np.array(thickness, copy=True)
    out[added] = thickness[indices[0][added], indices[1][added]]
    return out


def build_silhouette_mesh(
    thickness: np.ndarray, mask: np.ndarray, pitch: float
) -> trimesh.Trimesh:
    """Flat lithophane. Z=0 is the smooth back, on the bed. Z grows with darkness."""
    rows, cols = mask.shape
    if rows < 1 or cols < 1 or not mask.any():
        raise SystemExit("empty silhouette")

    vertex_rows = rows + 1
    vertex_cols = cols + 1
    per_layer = vertex_rows * vertex_cols
    height = np.zeros((vertex_rows, vertex_cols), dtype=np.float64)
    weight = np.zeros((vertex_rows, vertex_cols), dtype=np.float64)
    values = np.where(mask, thickness, 0.0)
    solid = mask.astype(np.float64)
    for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
        height[dj : rows + dj, di : cols + di] += values
        weight[dj : rows + dj, di : cols + di] += solid
    np.divide(height, weight, out=height, where=weight > 0)

    y_coords = (rows - np.arange(vertex_rows, dtype=np.float64)) * pitch
    x_coords = np.arange(vertex_cols, dtype=np.float64) * pitch
    x_grid, y_grid = np.meshgrid(x_coords, y_coords)
    front = np.stack([x_grid, y_grid, np.zeros_like(x_grid)], axis=-1)
    back = np.stack([x_grid, y_grid, height], axis=-1)
    vertices = np.concatenate([front.reshape(-1, 3), back.reshape(-1, 3)], axis=0)
    vertices = np.round(vertices, decimals=5)

    rr, cc = np.nonzero(mask)
    top_left = rr * vertex_cols + cc
    top_right = top_left + 1
    bot_left = (rr + 1) * vertex_cols + cc
    bot_right = bot_left + 1
    # Smooth back on the bed, outward normal -Z. Textured top, outward +Z.
    front_faces = np.concatenate(
        [
            np.stack([bot_left, top_left, top_right], axis=-1),
            np.stack([bot_left, top_right, bot_right], axis=-1),
        ],
        axis=0,
    )
    back_faces = np.concatenate(
        [
            np.stack([bot_left, bot_right, top_right], axis=-1),
            np.stack([bot_left, top_right, top_left], axis=-1),
        ],
        axis=0,
    ) + per_layer

    above = np.zeros((vertex_rows, cols), dtype=bool)
    below = np.zeros((vertex_rows, cols), dtype=bool)
    above[1:] = mask
    below[:rows] = mask
    left = np.zeros((rows, vertex_cols), dtype=bool)
    right = np.zeros((rows, vertex_cols), dtype=bool)
    right[:, :cols] = mask
    left[:, 1:] = mask

    faces = [front_faces, back_faces]
    faces.append(_horizontal_walls(below & ~above, per_layer, vertex_cols, outward_plus_y=True))
    faces.append(_horizontal_walls(above & ~below, per_layer, vertex_cols, outward_plus_y=False))
    faces.append(_vertical_walls(right & ~left, per_layer, vertex_cols, outward_plus_x=False))
    faces.append(_vertical_walls(left & ~right, per_layer, vertex_cols, outward_plus_x=True))

    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=np.concatenate([part for part in faces if len(part)], axis=0),
        process=False,
    )
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    return mesh


def _horizontal_walls(
    edges: np.ndarray, per_layer: int, vertex_cols: int, outward_plus_y: bool
) -> np.ndarray:
    jj, ii = np.nonzero(edges)
    if len(jj) == 0:
        return np.zeros((0, 3), dtype=np.int64)
    v0 = jj * vertex_cols + ii
    v1 = v0 + 1
    b0 = v0 + per_layer
    b1 = v1 + per_layer
    if outward_plus_y:
        return np.concatenate(
            [
                np.stack([v0, b0, b1], axis=-1),
                np.stack([v0, b1, v1], axis=-1),
            ],
            axis=0,
        )
    return np.concatenate(
        [
            np.stack([v0, v1, b1], axis=-1),
            np.stack([v0, b1, b0], axis=-1),
        ],
        axis=0,
    )


def _vertical_walls(
    edges: np.ndarray, per_layer: int, vertex_cols: int, outward_plus_x: bool
) -> np.ndarray:
    """edges[j, i] is the vertical grid edge at column i, spanning vertex rows j and j+1."""
    jj, ii = np.nonzero(edges)
    if len(jj) == 0:
        return np.zeros((0, 3), dtype=np.int64)
    # Higher Y is the smaller vertex-row index.
    v_hi = jj * vertex_cols + ii
    v_lo = (jj + 1) * vertex_cols + ii
    b_hi = v_hi + per_layer
    b_lo = v_lo + per_layer
    if outward_plus_x:
        return np.concatenate(
            [
                np.stack([v_lo, v_hi, b_hi], axis=-1),
                np.stack([v_lo, b_hi, b_lo], axis=-1),
            ],
            axis=0,
        )
    return np.concatenate(
        [
            np.stack([v_lo, b_lo, b_hi], axis=-1),
            np.stack([v_lo, b_hi, v_hi], axis=-1),
        ],
        axis=0,
    )


def nonmanifold_vertex_count(mesh: trimesh.Trimesh) -> int:
    """Vertices whose incident faces do not form a single fan."""
    link: dict[int, list[tuple[int, int]]] = {}
    for face in mesh.faces:
        for corner in range(3):
            link.setdefault(int(face[corner]), []).append(
                (int(face[(corner + 1) % 3]), int(face[(corner + 2) % 3]))
            )
    bad = 0
    for edges in link.values():
        neighbors: dict[int, list[int]] = {}
        for start, end in edges:
            neighbors.setdefault(start, []).append(end)
            neighbors.setdefault(end, []).append(start)
        if any(len(nodes) != 2 for nodes in neighbors.values()):
            bad += 1
            continue
        start = next(iter(neighbors))
        seen = {start}
        current = start
        previous = -1
        for _ in range(len(neighbors) + 1):
            nxt = [node for node in neighbors[current] if node != previous]
            if not nxt:
                break
            previous, current = current, nxt[0]
            if current == start:
                break
            seen.add(current)
        if len(seen) != len(neighbors):
            bad += 1
    return bad


def assert_solid(mesh: trimesh.Trimesh, euler: int = 2) -> None:
    if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise SystemExit("mesh is empty")
    if not mesh.is_watertight:
        raise SystemExit("mesh is not watertight")
    if not mesh.is_winding_consistent:
        raise SystemExit("mesh winding is inconsistent")
    if mesh.euler_number != euler:
        raise SystemExit(f"expected euler {euler}, got {mesh.euler_number}")
    if mesh.volume <= 0:
        raise SystemExit(f"non-positive volume: {mesh.volume}")
    if np.any(mesh.area_faces <= 1e-8):
        raise SystemExit("mesh has degenerate faces")
    _unique, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    if not np.all(counts == 2):
        raise SystemExit(f"non-manifold edges: {int(np.count_nonzero(counts != 2))}")
    pinched = nonmanifold_vertex_count(mesh)
    if pinched:
        raise SystemExit(f"non-manifold vertices: {pinched}")


def assert_silhouette(mesh: trimesh.Trimesh) -> None:
    assert_solid(mesh, euler=2)
    width, height, thick = (float(value) for value in mesh.extents)
    long_side = max(width, height)
    if not (100.0 <= long_side <= 150.0):
        raise SystemExit(f"long side {long_side:.2f} mm is outside 100–150 mm")
    if not (2.0 <= thick <= 4.5):
        raise SystemExit(f"thickness {thick:.2f} mm is outside the 2–4 mm plate range")
    if float(mesh.bounds[0, 2]) < -1e-4:
        raise SystemExit("model extends below the bed")
    back = mesh.vertices[:, 2]
    thin = float(back[back > 0.05].min()) if np.any(back > 0.05) else 0.0
    if thin < 0.8:
        raise SystemExit(f"thinnest solid is {thin:.2f} mm")
    print(
        f"mesh ok  vertices={len(mesh.vertices)} faces={len(mesh.faces)} "
        f"volume={mesh.volume:.1f} mm^3  "
        f"size={width:.2f} x {height:.2f} x {thick:.2f} mm (X x Y x Z)"
    )


def _box_volume(mask: np.ndarray, height: float, pitch: float) -> float:
    return float(mask.sum()) * pitch * pitch * height


def self_test_silhouette() -> None:
    """Winding and manifold checks on tiny masks before the cat is built."""
    pitch = 0.4
    thick = np.full((1, 1), 2.0)
    mesh = build_silhouette_mesh(thick, np.ones((1, 1), dtype=bool), pitch)
    assert_solid(mesh)
    _expect_volume(mesh, _box_volume(np.ones((1, 1)), 2.0, pitch))

    mask = np.zeros((1, 2), dtype=bool)
    mask[:] = True
    heights = np.array([[1.5, 3.0]])
    mesh = build_silhouette_mesh(heights, mask, pitch)
    # Corner heights average across the shared edge, so volume is pitch^2 * (h0+h1).
    assert_solid(mesh)
    _expect_volume(mesh, pitch * pitch * (1.5 + 3.0))

    diagonal = np.array([[True, False], [False, True]])
    bridged = _bridge_diagonal_contacts(diagonal)
    if bridged.sum() != 3:
        raise SystemExit("diagonal bridge did not add a connecting cell")
    mesh = build_silhouette_mesh(np.full(bridged.shape, 2.0), bridged, pitch)
    assert_solid(mesh)
    _expect_volume(mesh, _box_volume(bridged, 2.0, pitch))

    hole = np.ones((3, 3), dtype=bool)
    hole[1, 1] = False
    try:
        mesh = build_silhouette_mesh(np.full(hole.shape, 2.0), hole, pitch)
    except SystemExit:
        raise
    if mesh.euler_number == 2:
        raise SystemExit("a holed mask was treated as a simple solid")
    if not mesh.is_watertight or mesh.volume <= 0:
        raise SystemExit("holed silhouette is not a closed solid")
    print("silhouette self-test ok")


def _expect_volume(mesh: trimesh.Trimesh, expected_volume: float) -> None:
    if abs(mesh.volume - expected_volume) / expected_volume > 0.02:
        raise SystemExit(
            f"volume {mesh.volume:.4f} != expected {expected_volume:.4f}"
        )


def write_silhouette_preview(thickness: np.ndarray, mask: np.ndarray, path: Path) -> None:
    shown = (T_MAX_MM - thickness) / (T_MAX_MM - T_MIN_MM)
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    gray = np.clip(shown * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 0] = gray
    rgba[..., 1] = gray
    rgba[..., 2] = gray
    rgba[..., 3] = np.where(mask, 255, 0)
    Image.fromarray(rgba, mode="RGBA").save(path)


def _load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        loaded = loaded.dump(concatenate=True)
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="source cat photo (RGBA or RGB)")
    parser.add_argument(
        "--silhouette",
        action="store_true",
        help="cut away the background and write only the cat",
    )
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="optional grayscale preview of the thickness map",
    )
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    if args.output is None:
        name = "cat-lithophane-silhouette.3mf" if args.silhouette else "cat-lithophane.3mf"
        args.output = folder / name

    if args.silhouette:
        self_test_silhouette()
        thickness, mask, pitch = prepare_silhouette(args.image)
        print(
            f"silhouette cells={mask.shape[0]}x{mask.shape[1]} "
            f"pitch={pitch:.4f} mm filled={int(mask.sum())}"
        )
        if args.preview is not None:
            write_silhouette_preview(thickness, mask, args.preview)
            print(f"preview {args.preview}")
        mesh = build_silhouette_mesh(thickness, mask, pitch)
        assert_silhouette(mesh)
        geom_name = "cat-lithophane-silhouette"
        check = assert_silhouette
    else:
        lum = luminance_over_black(args.image)
        thickness = compose_thickness(lum)
        if args.preview is not None:
            write_preview(thickness, args.preview)
            print(f"preview {args.preview}")
        mesh = build_mesh(thickness)
        assert_printable(mesh)
        geom_name = "cat-lithophane"
        check = assert_printable

    scene = trimesh.Scene()
    scene.add_geometry(mesh, geom_name=geom_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scene.export(args.output)

    check(_load_mesh(args.output))
    size = args.output.stat().st_size
    if size < 1000:
        raise SystemExit(f"3MF looks empty ({size} bytes)")
    print(f"wrote {args.output} ({size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
