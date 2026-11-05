#!/usr/bin/env python3
"""Finder-style colour tags for Nautilus.

The tag lives on the file itself (xattr user.xdg.tags, also read by Dolphin), so it follows
renames and moves. Sidebar entries are ordinary GTK bookmarks to folders of symlinks, because
the Nautilus extension API cannot add a sidebar section; their labels double as tag names.
That API cannot draw dots either, so decorate() edits Nautilus's widgets from inside its process.
"""
import os
import subprocess
import sys

Nautilus = None
if __name__ != "__main__":  # the CLI runs from a timer and needs neither GTK nor a display
    try:
        import gi
        gi.require_version("Nautilus", "4.0")
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Nautilus
    except (ImportError, ValueError):  # tests must work without the bindings
        pass

ATTR = "user.xdg.tags"
COLORS = {
    "red": ("🔴", "Red", "#ff3b30"),
    "orange": ("🟠", "Orange", "#ff9500"),
    "yellow": ("🟡", "Yellow", "#ffcc00"),
    "green": ("🟢", "Green", "#34c759"),
    "blue": ("🔵", "Blue", "#007aff"),
    "purple": ("🟣", "Purple", "#af52de"),
    "gray": ("⚫", "Gray", "#8e8e93"),
}
OLD_NAMES = ("Crvena", "Narandžasta", "Žuta", "Zelena", "Plava", "Ljubičasta", "Siva")  # upgraded by init()
HOME = os.path.expanduser("~")
TAG_ROOT = os.path.join(HOME, ".local/share/file-tags")
BOOKMARKS = os.path.join(HOME, ".config/gtk-3.0/bookmarks")
# Not in hicolor: a stale icon-theme.cache there hides new icons until some other app rebuilds it
ICONS = os.path.join(TAG_ROOT, "icons")
OLD_EMBLEMS = os.path.join(HOME, ".local/share/icons/hicolor/scalable/emblems")
SKIP_DIRS = {"node_modules", "__pycache__"}
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><circle cx="8" cy="8" r="5" fill="{}"/></svg>\n'


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_tags(path):
    try:
        return os.fsdecode(os.getxattr(path, ATTR)).split(",")
    except OSError:  # no tags, a broken link, or a filesystem without xattrs
        return []


def add_link(path, color):
    folder = os.path.join(TAG_ROOT, color)
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(path))
    name, n = stem + ext, 1
    while os.path.lexists(os.path.join(folder, name)):
        if os.path.realpath(os.path.join(folder, name)) == path:
            return
        n += 1
        name = f"{stem} ({n}){ext}"
    os.symlink(path, os.path.join(folder, name))


def remove_link(path, color):
    folder = os.path.join(TAG_ROOT, color)
    if os.path.isdir(folder):
        for entry in os.scandir(folder):
            if entry.is_symlink() and os.path.realpath(entry.path) == path:
                os.unlink(entry.path)


def set_tag(path, color, on):
    path = os.path.realpath(path)  # the file may be picked from inside a tag folder
    tags = read_tags(path)
    if (color in tags) != on:
        # Other apps' tags in this attribute must survive
        tags = [t for t in tags if t != color] + ([color] if on else [])
        if tags:
            os.setxattr(path, ATTR, os.fsencode(",".join(tags)))
        else:
            os.removexattr(path, ATTR)
    (add_link if on else remove_link)(path, color)


def rescan(root=HOME):
    """Bring the symlink folders back in line with the xattrs; only ever touches symlinks."""
    # shortcut: a link to an unplugged drive is pruned and only home is rescanned, walk mounts too if tags on external drives matter
    for color in COLORS:
        folder = os.path.join(TAG_ROOT, color)
        if os.path.isdir(folder):
            for entry in os.scandir(folder):
                if entry.is_symlink() and color not in read_tags(entry.path):
                    os.unlink(entry.path)
    for parent, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        for name in dirs + files:
            path = os.path.join(parent, name)
            if not os.path.islink(path):
                for tag in read_tags(path):
                    if tag in COLORS:
                        add_link(path, tag)


def tag_color(uri):
    color = uri.rpartition("/")[2]
    return color if color in COLORS and uri == f"file://{TAG_ROOT}/{color}" else None


def init():
    """Create tag folders, emblem icons and sidebar bookmarks. Safe to re-run; keeps renames."""
    os.makedirs(ICONS, exist_ok=True)
    os.makedirs(os.path.dirname(BOOKMARKS), exist_ok=True)
    lines = read_text(BOOKMARKS).splitlines() if os.path.exists(BOOKMARKS) else []
    present = set()
    for i, line in enumerate(lines):
        uri, _, label = line.partition(" ")
        color = tag_color(uri)
        if color:
            present.add(color)
            # Earlier versions put the emoji in the label and used Serbian defaults; user renames stay
            label = label.removeprefix(COLORS[color][0]).strip()
            lines[i] = f"{uri} {COLORS[color][1] if not label or label in OLD_NAMES else label}"
    for color, (_, name, fill) in COLORS.items():
        os.makedirs(os.path.join(TAG_ROOT, color), exist_ok=True)
        with open(os.path.join(ICONS, f"emblem-tag-{color}.svg"), "w") as svg:
            svg.write(SVG.format(fill))
        if os.path.exists(os.path.join(OLD_EMBLEMS, f"emblem-tag-{color}.svg")):
            os.unlink(os.path.join(OLD_EMBLEMS, f"emblem-tag-{color}.svg"))
        if color not in present:
            lines.append(f"file://{TAG_ROOT}/{color} {name}")
    with open(BOOKMARKS + ".tmp", "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    os.replace(BOOKMARKS + ".tmp", BOOKMARKS)  # a crash must not leave the user's bookmarks cut short


def labels():
    """Tag names as they read in the sidebar, so renaming the bookmark renames the tag."""
    names = {color: name for color, (_, name, _) in COLORS.items()}
    try:
        lines = read_text(BOOKMARKS).splitlines()
    except OSError:
        return names
    for line in lines:
        uri, _, label = line.partition(" ")
        if label and tag_color(uri):
            names[tag_color(uri)] = label
    return names


def walk_mapped(widget):
    if widget.get_mapped():
        yield widget
        child = widget.get_first_child()
        while child:
            yield from walk_mapped(child)
            child = child.get_next_sibling()


def dress_sidebar_row(row):
    color = tag_color(row.get_property("uri") or "")
    if color:
        icon = Gio.ThemedIcon.new(f"emblem-tag-{color}")
        if not icon.equal(row.get_property("start-icon")):
            row.set_property("start-icon", icon)
            row.add_css_class("file-tag-row")


def dress_grid_cell(labels_box):
    """Move the emblems from beside the icon to before the name, as Finder shows them."""
    picture_row, name = labels_box.get_prev_sibling(), labels_box.get_first_child()
    emblems = picture_row.get_last_child() if picture_row else None
    # Anything else means this cell is done, or a future Nautilus laid it out differently
    if isinstance(name, Gtk.Label) and isinstance(emblems, Gtk.Box):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2, halign=Gtk.Align.CENTER)
        picture_row.remove(emblems)
        labels_box.remove(name)
        picture_row.set_margin_end(18)  # the emblem column set the cell's width, keep it or names wrap early
        emblems.set_orientation(Gtk.Orientation.HORIZONTAL)
        emblems.set_size_request(-1, -1)
        emblems.set_margin_start(0)
        emblems.set_spacing(0)
        emblems.set_valign(Gtk.Align.START)
        name.set_natural_wrap_mode(Gtk.NaturalWrapMode.NONE)  # else the centred row is narrower than the cell
        row.append(emblems)
        row.append(name)
        labels_box.prepend(row)


def in_tag_folder(path):
    folder, _, color = os.path.dirname(path).rpartition("/")
    return folder == TAG_ROOT and color in COLORS


def hide_link_emblem(cell):
    """Everything in a tag folder is a link, so the arrow says nothing there."""
    for widget in walk_mapped(cell):
        if isinstance(widget, Gtk.Image) and isinstance(widget.get_gicon(), Gio.ThemedIcon):
            if any("symbolic-link" in name for name in widget.get_gicon().get_names()):
                item = cell.get_property("item")
                file = item.get_property("file") if item else None
                path = file.get_location().get_path() if file else None
                if path and in_tag_folder(path):
                    widget.set_visible(False)


def setup_display():
    Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(ICONS)
    # Themes dim sidebar icons, which would mute the tag colours
    provider = Gtk.CssProvider()
    provider.load_from_string(".file-tag-row .sidebar-icon { opacity: 1; }")
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)


def decorate():
    # shortcut: polls because rows and cells are created with no signal an extension can reach, a 0.5s dot delay on new cells is the cost
    for window in Gtk.Window.list_toplevels():
        for widget in walk_mapped(window):
            kind = GObject.type_name(widget)
            if kind == "NautilusGtkSidebarRow":
                dress_sidebar_row(widget)
            elif kind in ("NautilusGridCell", "NautilusNameCell"):
                hide_link_emblem(widget)
            elif widget.has_css_class("icon-ui-labels-box"):
                dress_grid_cell(widget)
    return GLib.SOURCE_CONTINUE


if Nautilus:
    class FileTags(GObject.GObject, Nautilus.MenuProvider, Nautilus.InfoProvider):
        def __init__(self):
            super().__init__()
            setup_display()
            GLib.timeout_add(500, decorate)

        def update_file_info(self, file):
            path = file.get_location().get_path()
            for tag in read_tags(path) if path else []:
                if tag in COLORS:
                    file.add_emblem(f"tag-{tag}")

        def get_file_items(self, files):
            paths = [f.get_location().get_path() for f in files]
            if not paths or not all(paths):
                return []
            top = Nautilus.MenuItem(name="FileTags::menu", label="Tags")
            submenu = Nautilus.Menu()
            top.set_submenu(submenu)
            for color, label in labels().items():
                on = all(color in read_tags(p) for p in paths)
                item = Nautilus.MenuItem(name=f"FileTags::{color}", label=f"{'✓ ' if on else ''}{COLORS[color][0]} {label}")
                item.connect("activate", self._toggle, files, color, not on)
                submenu.append_item(item)
            return [top]

        def _toggle(self, _item, files, color, on):
            failed = []
            for file in files:
                path = file.get_location().get_path()
                try:
                    set_tag(path, color, on)
                except OSError as err:  # read-only file, or a filesystem like FAT without xattrs
                    failed.append(f"{os.path.basename(path)}: {err.strerror}")
                file.invalidate_extension_info()
            if failed:
                subprocess.run(["notify-send", "Could not change tag", "\n".join(failed)], check=False)


if __name__ == "__main__":
    {"init": init, "rescan": rescan}[sys.argv[1]]()
