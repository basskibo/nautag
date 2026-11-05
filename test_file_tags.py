#!/usr/bin/env python3
"""Run: python3 test_file_tags.py (uses a throwaway HOME, never the real one)."""
import os
import tempfile
import unittest

HOME = tempfile.mkdtemp(prefix="file-tags-", dir=os.path.dirname(os.path.abspath(__file__)))
os.environ["HOME"] = HOME
import file_tags as ft  # noqa: E402


def touch(rel, text="x"):
    path = os.path.join(HOME, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def links(color):
    folder = os.path.join(ft.TAG_ROOT, color)
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class Tags(unittest.TestCase):
    def setUp(self):
        os.makedirs(os.path.dirname(ft.BOOKMARKS), exist_ok=True)
        with open(ft.BOOKMARKS, "w") as f:
            f.write("")

    def test_toggle_keeps_foreign_tags_and_cleans_up(self):
        p = touch("a/foreign.txt")
        os.setxattr(p, ft.ATTR, b"kde-tag")
        ft.set_tag(p, "red", True)
        self.assertEqual(ft.read_tags(p), ["kde-tag", "red"])
        ft.set_tag(p, "red", False)
        self.assertEqual(ft.read_tags(p), ["kde-tag"])
        self.assertNotIn("foreign.txt", links("red"))
        os.removexattr(p, ft.ATTR)
        ft.set_tag(p, "blue", True)
        ft.set_tag(p, "blue", False)
        with self.assertRaises(OSError):
            os.getxattr(p, ft.ATTR)

    def test_untag_from_inside_tag_folder_hits_real_file(self):
        p = touch("b/viaspot.txt")
        ft.set_tag(p, "green", True)
        ft.set_tag(os.path.join(ft.TAG_ROOT, "green", "viaspot.txt"), "green", False)
        self.assertNotIn("green", ft.read_tags(p))
        self.assertTrue(os.path.isfile(p) and not os.path.islink(p))

    def test_same_name_in_two_folders(self):
        a, b = touch("c/one/same.txt"), touch("c/two/same.txt")
        ft.set_tag(a, "yellow", True)
        ft.set_tag(b, "yellow", True)
        ft.set_tag(a, "yellow", True)  # idempotent, no third link
        self.assertEqual(links("yellow"), ["same (2).txt", "same.txt"])

    def test_rescan_follows_move_and_never_deletes_files(self):
        p = touch("d/moved.txt", "keep me")
        ft.set_tag(p, "purple", True)
        new = os.path.join(HOME, "d/renamed.txt")
        os.rename(p, new)
        ft.rescan(HOME)
        self.assertEqual(links("purple"), ["renamed.txt"])
        with open(os.path.join(ft.TAG_ROOT, "purple", "renamed.txt")) as f:
            self.assertEqual(f.read(), "keep me")
        os.removexattr(new, ft.ATTR)
        ft.rescan(HOME)
        self.assertEqual(links("purple"), [])
        self.assertTrue(os.path.exists(new))

    def test_rescan_keeps_tagged_file_in_hidden_dir(self):
        p = touch(".hidden/secret.txt")
        ft.set_tag(p, "gray", True)
        ft.rescan(HOME)
        self.assertEqual(links("gray"), ["secret.txt"])

    def test_init_is_idempotent_and_keeps_bookmarks(self):
        os.makedirs(os.path.dirname(ft.BOOKMARKS), exist_ok=True)
        with open(ft.BOOKMARKS, "w") as f:
            f.write("file:///home/me/Documents")  # no trailing newline
        ft.init()
        ft.init()
        lines = ft.read_text(ft.BOOKMARKS).splitlines()
        self.assertEqual(lines[0], "file:///home/me/Documents")
        self.assertEqual(len(lines), 1 + len(ft.COLORS))

    def test_renamed_bookmark_renames_tag(self):
        ft.init()
        text = ft.read_text(ft.BOOKMARKS).replace(" Red", " Posao")
        with open(ft.BOOKMARKS, "w", encoding="utf-8") as f:
            f.write(text)
        ft.init()
        self.assertEqual(ft.labels()["red"], "Posao")
        self.assertEqual(ft.labels()["blue"], "Blue")

    def test_init_moves_icons_out_of_hicolor(self):
        old = os.path.join(ft.OLD_EMBLEMS, "emblem-tag-red.svg")
        other = os.path.join(ft.OLD_EMBLEMS, "someone-elses.svg")
        os.makedirs(ft.OLD_EMBLEMS, exist_ok=True)
        for path in (old, other):
            open(path, "w").close()
        ft.init()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(other))
        self.assertTrue(os.path.getsize(os.path.join(ft.ICONS, "emblem-tag-red.svg")))

    def test_in_tag_folder(self):
        self.assertTrue(ft.in_tag_folder(os.path.join(ft.TAG_ROOT, "red", "a.txt")))
        self.assertFalse(ft.in_tag_folder(os.path.join(ft.TAG_ROOT, "icons", "a.svg")))
        self.assertFalse(ft.in_tag_folder(os.path.join(ft.TAG_ROOT, "red", "sub", "a.txt")))
        self.assertFalse(ft.in_tag_folder(os.path.join(HOME, "red", "a.txt")))

    def test_init_strips_old_emoji_labels_only(self):
        with open(ft.BOOKMARKS, "w", encoding="utf-8") as f:
            f.write(f"file://{ft.TAG_ROOT}/blue 🔵 Plava\nfile://{ft.TAG_ROOT}/red top\nfile:///x 🔵 Moje\n")
        ft.init()
        lines = ft.read_text(ft.BOOKMARKS).splitlines()
        self.assertEqual(lines[:3], [f"file://{ft.TAG_ROOT}/blue Blue", f"file://{ft.TAG_ROOT}/red top", "file:///x 🔵 Moje"])
        self.assertEqual(len(lines), 1 + len(ft.COLORS))


if __name__ == "__main__":
    import shutil
    try:
        unittest.main(exit=False)
    finally:
        shutil.rmtree(HOME)
