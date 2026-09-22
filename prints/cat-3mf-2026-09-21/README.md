# Cat lithophanes

Two printable meshes of the orange Bengal / tabby photo. Bright fur and the green eyes are thin, so they glow when backlit. Dark stripes are thicker.

## Just the cat

`cat-lithophane-silhouette.3mf` cuts the background away. The outline is the cat, including the gap under the chest between the paws. Where the photo itself crops the body, that edge follows the crop.

| Axis | Role | Size |
| --- | --- | --- |
| X | width, head toward X = 0 | 105.6 mm |
| Y | height, ears toward +Y | 130.0 mm |
| Z | thickness | 1.0–3.4 mm (peak 3.35 mm) |

Lay it flat. The smooth back is Z = 0 and sits on the bed; the textured face points up. On the bed the head is to the left and the ears point toward +Y.

**Layer height: 0.12 mm.** Thickness is the picture, so a finer layer keeps more fur tones. 0.16 mm prints faster and looks a little flatter. Use a 0.4 mm line width, 100% infill, and 3–4 walls with thin-wall detection on. A 3 mm brim helps the ears and paw tips stay down. After printing, look through the smooth side with the textured side toward the light.

This one lies flat because the outline overhangs: the chest and head stick out past the paws. Standing it up would need supports.

## Framed plate

`cat-lithophane.3mf` keeps the black background as a solid frame. It is 100.4 mm wide, 126.0 mm tall, and 1.0–3.4 mm thick, already standing on a 3.2 mm foot. Put that foot on the bed and leave the plate vertical. **Layer height: 0.16 mm** (0.12 mm for sharper stripes). Use a 5–8 mm brim; the footprint is only 3.4 mm deep. The flat face is the front, and the cat’s head is on the left when you look at that face.

## Both files

- Filament: white, natural, or other translucent PLA.
- Infill: 100%. Gaps in the print show up as holes in the picture.
- Line width: 0.4 mm.

A lithophane shows the photo only when light comes through it. An opaque relief would be a thicker plaque, about 80–120 mm tall, viewed in room light, and the eyes would not glow.

Rebuild with `python3 generate_lithophane.py photo.png` for the framed plate, or add `--silhouette` for the cut-out cat. The script checks that each mesh is a non-empty watertight solid before it writes the 3MF.
