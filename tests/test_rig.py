"""Rig layer: rotation, joints, and ground lock. Run: python -m unittest"""
import unittest

from PIL import Image, ImageDraw

from pixelart_mcp import rig

RED, BLUE, DARK = (200, 40, 40, 255), (40, 60, 200, 255), (20, 20, 30, 255)


def colors(img):
    return {img.getpixel((x, y)) for x in range(img.width) for y in range(img.height)
            if img.getpixel((x, y))[3]}


def limb_sheet():
    """24x24: a 4x8 'thigh' at (0,0) and a 4x6 'shin' at (8,0)."""
    img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 3, 7], fill=RED)
    d.rectangle([0, 0, 0, 7], fill=DARK)
    d.rectangle([8, 0, 11, 5], fill=BLUE)
    return img


def limb_rig(**shin):
    return rig.normalize_rig({
        "frame_width": 24, "frame_height": 24,
        "parts": [
            {"name": "leg", "x": 0, "y": 0, "width": 4, "height": 8, "at_x": 10, "at_y": 2},
            {"name": "shin", "x": 8, "y": 0, "width": 4, "height": 6, "parent": "leg", **shin},
        ],
    })


class RotationTest(unittest.TestCase):
    def test_rotation_never_invents_colors(self):
        src = limb_sheet()
        for deg in (7, 23, 45, 61, 90, 133):
            frame = rig.compose_frame(src, limb_rig(), {"leg": {"angle": [[0, deg]]}}, 0.0)
            self.assertLessEqual(colors(frame), colors(src), f"new colors at {deg} degrees")

    def test_zero_angle_is_an_exact_stamp(self):
        src = limb_sheet()
        frame = rig.compose_frame(src, limb_rig(), {}, 0.0)
        self.assertEqual(frame.getpixel((10, 2)), DARK)
        self.assertEqual(frame.getpixel((13, 8)), RED)
        self.assertEqual(frame.getpixel((10, 9)), BLUE)  # shin joint shares the thigh's last row

    def test_positive_angle_swings_hanging_end_forward(self):
        src = limb_sheet()
        frame = rig.compose_frame(src, limb_rig(), {"leg": {"angle": [[0, 60]]}}, 0.0)
        xs = [x for x in range(24) for y in range(24) if frame.getpixel((x, y)) == BLUE]
        self.assertGreater(min(xs), 14, "the shin should ride the thigh forward (+x)")


class JointTest(unittest.TestCase):
    def test_child_snaps_to_parent_joint(self):
        r = rig.parts_by_name(limb_rig())
        self.assertEqual((r["shin"]["at_x"], r["shin"]["at_y"]), (10, 9))

    def test_explicit_placement_wins(self):
        r = rig.parts_by_name(limb_rig(at_x=1, at_y=1))
        self.assertEqual((r["shin"]["at_x"], r["shin"]["at_y"]), (1, 1))

    def test_bad_parents_are_reported(self):
        with self.assertRaisesRegex(ValueError, "not a part"):
            rig.normalize_rig({"parts": [{"name": "a", "x": 0, "y": 0, "width": 1,
                                          "height": 1, "parent": "ghost"}]})
        with self.assertRaisesRegex(ValueError, "Parent loop"):
            rig.normalize_rig({"parts": [
                {"name": "a", "x": 0, "y": 0, "width": 1, "height": 1, "parent": "b"},
                {"name": "b", "x": 0, "y": 0, "width": 1, "height": 1, "parent": "a"}]})
        with self.assertRaisesRegex(ValueError, "outside"):
            rig.normalize_rig({"parts": [{"name": "a", "x": 0, "y": 0, "width": 2,
                                          "height": 2, "pivot_x": 5}]})


class MotionTest(unittest.TestCase):
    def test_ground_lock_keeps_the_floor(self):
        src = limb_sheet()
        frames = rig.render_cycle(src, limb_rig(), {"leg": {"angle": [[0, 30], [0.5, -30]]}},
                                  8, ground=True)
        floors = {rig._lowest_opaque_row(f) for f in frames}
        self.assertEqual(len(floors), 1)

    def test_renders_are_deterministic(self):
        src = limb_sheet()
        motion = rig.resolve_motion("walk", None)
        a = rig.render_cycle(src, limb_rig(), motion["parts"], 8, ground=True)
        b = rig.render_cycle(src, limb_rig(), motion["parts"], 8, ground=True)
        self.assertEqual([f.tobytes() for f in a], [f.tobytes() for f in b])

    def test_full_motion_object_round_trips(self):
        preset = {k: v for k, v in rig.MOTIONS["run"].items() if k != "notes"}
        m = rig.resolve_motion(None, preset)
        self.assertTrue(m["ground"])
        self.assertEqual(m["lift"], rig.MOTIONS["run"]["lift"])
        self.assertIn("leg_front", m["parts"])

    def test_angle_is_not_rounded(self):
        v = rig.evaluate_part({"a": {"angle": [[0, 0], [0.5, 10]]}}, "a", 0.1)
        self.assertNotEqual(v["angle"], round(v["angle"]))


if __name__ == "__main__":
    unittest.main()
