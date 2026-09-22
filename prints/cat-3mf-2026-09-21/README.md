# Cat prints

Three meshes from the orange Bengal / tabby photo.

## Upright standee

`cat-upright.3mf` is the cat with the black background cut away. It stands on a desk like a photo standee. In the file, Z is up and the base is already on Z = 0, so a 3D view shows it standing.

| Axis | Role | Size |
| --- | --- | --- |
| X | depth, front at X = 0, rear foot toward +X | 54.0 mm |
| Y | width | 106.7 mm |
| Z | height | 120.0 mm |

The cat is a solid 4 mm extrusion. An 8 mm plinth runs 22 mm in front of the cat and 28 mm behind it, and a rear foot braces the back. The paws sit in the plinth. The opening under the chest goes through from front to back.

**Print it upright.** Put the base on the bed. Leave the rear foot pointing toward the back of the printer. No supports: above the plinth the outline stays shallow enough to print, and the rear foot slopes inward as it rises.

- Layer height: 0.20 mm
- Line width: 0.4 mm
- Walls: 4
- Infill: 40%
- Brim: optional, 3 mm
- Filament: any PLA. This file is a solid standee, not a lithophane.

Look at the front from X = 0. The cat’s head is on the left.

## Flat lithophane, no background

`cat-lithophane-no-bg.3mf` is the same cut-out as a backlit plate, 105.6 mm wide, 130.0 mm tall, and 1.0–3.4 mm thick. It lies flat: the smooth back is on the bed and the textured face is up. **Layer height: 0.12 mm.** Use white or natural PLA, 100% infill, a 0.4 mm line width, and a 3 mm brim. After printing, look through the smooth side with the light on the textured side.

## Framed lithophane

`cat-lithophane.3mf` keeps the black background as a solid frame. It is 100.4 mm wide, 126.0 mm tall, and 1.0–3.4 mm thick, already standing on a 3.2 mm foot. Put that foot on the bed and leave the plate vertical. **Layer height: 0.16 mm.** Use a 5–8 mm brim. The flat face is the front, and the cat’s head is on the left when you look at that face. White or natural PLA, 100% infill, 0.4 mm lines.

A lithophane shows the photo only when light comes through it. The upright file is the one that stands on a desk in ordinary light.

Rebuild with `python3 generate_lithophane.py photo.png` for the framed plate, `--silhouette` for the flat cut-out, or `--upright` for the standee. The script checks that each mesh is a non-empty watertight solid before it writes the 3MF.
