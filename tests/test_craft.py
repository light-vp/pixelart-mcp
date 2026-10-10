"""Craft layer: form shading and lint. Run: python -m unittest"""
import unittest

from PIL import Image, ImageDraw

from pixelart_mcp import craft

BASE = (194, 46, 46, 255)


def disc(size=32):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([2, 2, size - 3, size - 3], fill=BASE)
    return img


def shade(mode, light="top_left"):
    img = disc()
    mask = {(x, y) for x in range(img.width) for y in range(img.height) if img.getpixel((x, y))[3]}
    ramp, base_idx = craft._resolve_form_ramp(BASE, None)
    fn = {"sphere": craft.shade_sphere, "form": craft.shade_form}[mode]
    fn(img, mask, ramp, light, base_idx)
    return img, mask


def luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


class ShadingTest(unittest.TestCase):
    def test_base_color_dominates(self):
        for mode in ("sphere", "form"):
            img, mask = shade(mode)
            counts = {}
            for p in mask:
                c = img.getpixel(p)
                counts[c] = counts.get(c, 0) + 1
            top = max(counts, key=counts.get)
            self.assertEqual(top[:3], BASE[:3], mode)
            self.assertLess(counts[top] / len(mask), 0.65, mode)

    def test_light_side_is_brighter(self):
        for mode in ("sphere", "form"):
            img, mask = shade(mode, "top_left")
            lit = [luma(img.getpixel(p)) for p in mask if p[0] + p[1] < 26]
            dark = [luma(img.getpixel(p)) for p in mask if p[0] + p[1] > 36]
            self.assertGreater(sum(lit) / len(lit), sum(dark) / len(dark), mode)

    def test_no_orphan_pixels(self):
        img, mask = shade("form")
        for (x, y) in mask:
            c = img.getpixel((x, y))
            nbs = [q for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)) if q in mask]
            if len(nbs) >= 2:
                self.assertTrue(any(img.getpixel(q) == c for q in nbs), (x, y))


class LintTest(unittest.TestCase):
    def flat(self):
        img = Image.new("RGBA", (16, 16), (60, 90, 160, 255))
        return img

    def test_near_duplicates_merge(self):
        img = self.flat()
        ImageDraw.Draw(img).rectangle([0, 0, 7, 15], fill=(62, 91, 158, 255))
        rep = craft.lint(img, fix=True)
        self.assertEqual(rep["near_duplicates"], 1)
        self.assertEqual(len(img.getcolors()), 1)

    def test_low_contrast_speck_is_cleaned_glint_is_kept(self):
        img = self.flat()
        img.putpixel((4, 4), (80, 108, 180, 255))    # noise: visible, but only just
        img.putpixel((11, 11), (255, 255, 255, 255))  # deliberate glint
        rep = craft.lint(img, fix=True)
        self.assertEqual(rep["strays"], 1)
        self.assertEqual(img.getpixel((4, 4)), (60, 90, 160, 255))
        self.assertEqual(img.getpixel((11, 11)), (255, 255, 255, 255))

    def test_dither_is_not_noise(self):
        img = self.flat()
        for y in range(0, 16, 4):
            for x in range(0, 16, 4):
                img.putpixel((x, y), (80, 110, 175, 255))
        self.assertEqual(craft.lint(img)["strays"], 0)

    def test_outline_color_reuses_palette(self):
        want = craft.darken_for_outline(BASE[:3])
        near = (want[0] + 3, want[1] + 2, want[2])
        self.assertEqual(craft.outline_color(BASE[:3], [near]), near)
        self.assertEqual(craft.outline_color(BASE[:3], [(250, 250, 250)]), want)


if __name__ == "__main__":
    unittest.main()
