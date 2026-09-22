#!/usr/bin/env python3
"""Build a printable lithophane plate from the Bengal cat photo.

Brightness becomes thickness: bright fur and the green eyes are thin
(they glow when backlit); the black background is thick and stays dark.
The plate is oriented upright for FDM, with a full-thickness foot on Z=0.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="source cat photo (RGBA or RGB)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "cat-lithophane.3mf",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="optional grayscale preview of the thickness map",
    )
    args = parser.parse_args()

    lum = luminance_over_black(args.image)
    thickness = compose_thickness(lum)
    if args.preview is not None:
        write_preview(thickness, args.preview)
        print(f"preview {args.preview}")

    mesh = build_mesh(thickness)
    assert_printable(mesh)

    scene = trimesh.Scene()
    scene.add_geometry(mesh, geom_name="cat-lithophane")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scene.export(args.output)

    loaded = trimesh.load(args.output, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        loaded = loaded.dump(concatenate=True)
    assert_printable(loaded)
    size = args.output.stat().st_size
    if size < 1000:
        raise SystemExit(f"3MF looks empty ({size} bytes)")
    print(f"wrote {args.output} ({size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
