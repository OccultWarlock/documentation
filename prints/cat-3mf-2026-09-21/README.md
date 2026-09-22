# Cat lithophane

Printable lithophane of the orange Bengal / tabby photo (neon-green eyes, black background). Bright fur and the eyes are thin, so they glow when the plate is backlit. Black fur, stripes, and the background are thicker and stay dark.

`cat-lithophane.3mf` is a single solid, manifold mesh in millimeters.

## Size

| Axis | Role | Size |
| --- | --- | --- |
| Y | width | 100.4 mm |
| Z | height | 126.0 mm |
| X | thickness | 1.0–3.4 mm |

The long side is the 126 mm height. Highlights are about 1.0 mm thick; the black background, the 1.6 mm side frame, the 3.2 mm top frame, and the foot are 3.4 mm thick.

## Orientation

The plate is already standing. Put the bottom face on the bed. That face is a full-thickness foot about 3.2 mm tall, so the first layers are a 3.4 mm × 100.4 mm strip.

Keep the plate vertical so the layer height draws the picture.

The flat face (X = 0) is the front. Look at that face, with the lamp behind the textured side. The cat’s head is on the left. If a slicer auto-orients the part onto its flat face, stand it back up on the foot.

## Suggested slice

- **Layer height:** 0.16 mm. Use 0.12 mm if you want crisper stripes and eyes (the plate is about 790 layers at 0.16 mm, about 1050 at 0.12 mm).
- **Line width:** 0.4 mm, matching the mesh sample pitch.
- **Walls:** 3 or 4, with thin-wall detection on. The bright areas are only about 1 mm thick.
- **Infill:** 100%. A lithophane has to be solid or light leaks through the gaps.
- **Filament:** white, natural, or other translucent PLA. Dark filament will not show the picture.
- **Brim:** 5–8 mm. The part is 126 mm tall and only 3.4 mm deep, so it tips easily.
- Back-face slopes stay within about 50° of vertical, so the thickness steps do not become steep overhangs.

## Lithophane vs opaque relief

This file is a **lithophane**. Room light only shows a faint relief. The photo appears when you backlight it: thin regions transmit light, thick regions block it. That suits this picture, because the black field stays dark and the fur and green eyes light up.

An **opaque relief** would be a thicker plaque, usually 80–120 mm tall, with the photo raised on a solid backing and viewed by reflected light. It does not need translucent filament or a lamp behind it, and the eyes would not glow. Use a relief only if the print will be seen in ordinary room light and never backlit.

Rebuild the plate with `python3 generate_lithophane.py photo.png` (Pillow, NumPy, Trimesh, SciPy). The script checks that the mesh is a non-empty, watertight solid before it writes the 3MF.
