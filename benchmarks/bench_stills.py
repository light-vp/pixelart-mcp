"""Stills benchmark: re-render every scripted piece and lint it.

Usage:  python benchmarks/bench_stills.py [--out DIR] [REPO_ROOT ...]

For each repo root given (default: this checkout) it copies the tree to a
scratch directory, runs every script in benchmarks/runs/*/scripts plus the
examples' still demos there — the committed images are never touched — and
lints the PNGs with THIS checkout's linter, so two roots (say a worktree of
the previous release and this one) are scored by one ruler.

Prints a per-piece table and totals. With --out, also writes compare.png:
one row per piece, one column per root, for judging by eye what a score
can't capture.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PIL import Image, ImageDraw  # noqa: E402

from pixelart_mcp import craft  # noqa: E402

STILL_DEMOS = ("demo_apple.py", "demo_bottle.py")


def pieces(root: str) -> list[tuple[str, str, str]]:
    """(name, script, png) for every scripted still under root."""
    out = []
    for script in sorted(glob.glob(f"{root}/benchmarks/runs/*/scripts/*.py")):
        name = os.path.splitext(os.path.basename(script))[0]
        if name.startswith("make_"):
            continue
        out.append((name, script, os.path.join(os.path.dirname(os.path.dirname(script)), f"{name}.png")))
    for demo in STILL_DEMOS:
        name = demo[5:-3]
        out.append((f"ex-{name}", f"{root}/benchmarks/examples/{demo}",
                    f"{root}/benchmarks/examples/{name}.png"))
    return out


def run(root: str, scratch: str) -> dict[str, dict]:
    work = os.path.join(scratch, f"tree{len(os.listdir(scratch))}")
    shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    results = {}
    for name, script, png in pieces(work):
        proc = subprocess.run([sys.executable, script], capture_output=True, text=True, cwd=work)
        if proc.returncode != 0 or not os.path.exists(png):
            results[name] = {"error": (proc.stderr or proc.stdout).strip().splitlines()[-1:]}
            continue
        img = Image.open(png).convert("RGBA")
        rep = craft.lint(img)
        results[name] = {k: rep[k] for k in ("score", "colors", "near_duplicates", "strays")}
        results[name]["image"] = img
    return results


def compare_sheet(runs: dict[str, dict], names: list[str], path: str, cell: int = 160) -> None:
    cols = len(runs)
    sheet = Image.new("RGBA", (cols * (cell + 8) + 120, len(names) * (cell + 8)), (40, 40, 46, 255))
    d = ImageDraw.Draw(sheet)
    for row, n in enumerate(names):
        y = row * (cell + 8)
        d.text((4, y + cell // 2), n, fill=(220, 220, 230, 255))
        for col, r in enumerate(runs.values()):
            v = r.get(n, {})
            img = v.get("image")
            if img is None:
                continue
            k = max(1, cell // max(img.size))
            sheet.alpha_composite(img.resize((img.width * k, img.height * k), Image.NEAREST),
                                  (120 + col * (cell + 8), y))
            d.text((120 + col * (cell + 8) + 2, y + 2), f"{v['score']}",
                   fill=(255, 230, 120, 255))
    sheet.save(path)


def main(argv: list[str]) -> None:
    out = None
    if argv[:1] == ["--out"]:
        out, argv = argv[1], argv[2:]
    roots = argv or [os.path.dirname(HERE)]
    with tempfile.TemporaryDirectory() as scratch:
        runs = {root: run(root, scratch) for root in roots}
    names = sorted({n for r in runs.values() for n in r})
    head = f"{'piece':<16}" + "".join(f" | {os.path.basename(r.rstrip('/'))[:22]:>22}" for r in roots)
    print(head + "\n" + "-" * len(head))
    for n in names:
        cells = []
        for r in roots:
            v = runs[r].get(n, {})
            cells.append("error" if "error" in v else
                         f"{v['score']:>3} c{v['colors']:<3} d{v['near_duplicates']:<2} s{v['strays']:<3}")
        print(f"{n:<16}" + "".join(f" | {c:>22}" for c in cells))
    for r in roots:
        ok = [v for v in runs[r].values() if "error" not in v]
        tot = {k: sum(v[k] for v in ok) for k in ("score", "near_duplicates", "strays")}
        print(f"\n{r}: mean score {tot['score'] / max(1, len(ok)):.1f}, "
              f"near-dupes {tot['near_duplicates']}, strays {tot['strays']}, "
              f"errors {len(runs[r]) - len(ok)}")
    if out:
        os.makedirs(out, exist_ok=True)
        compare_sheet(runs, names, os.path.join(out, "compare.png"))
        print(f"wrote {os.path.join(out, 'compare.png')}")


if __name__ == "__main__":
    main(sys.argv[1:])
