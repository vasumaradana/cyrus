"""
test_permission_scan.py — verify PermissionWatcher UIA detection

Run this while a VS Code permission dialog ("Allow this bash command?") is visible.
Prints everything found in the VS Code UIA tree so we can see what's there.

Usage:
    python test_permission_scan.py
"""

import logging
import time

import comtypes
import uiautomation as auto

log = logging.getLogger(__name__)

VSCODE_TITLE = "Visual Studio Code"


def walk_and_print(ctrl, d=0, max_depth=15, prefix=""):
    if d > max_depth:
        return
    try:
        name = (ctrl.Name or "").strip()
        ctype = ctrl.ControlTypeName or ""
        cls = ctrl.ClassName or ""
        if name or cls:
            marker = " *** ALLOW THIS ***" if "Allow this" in name else ""
            marker = marker or (
                " *** YES ***" if name.lower() in ("yes", "1 yes", "yes, allow") else ""
            )
            marker = marker or (
                " *** PERMISSION ***" if "requesting permission" in name.lower() else ""
            )
            print(f"{'  ' * d}[{ctype}] name={name!r:50s} class={cls!r}{marker}")
    except Exception as e:
        print(f"{'  ' * d}<error: {e}>")
    try:
        child = ctrl.GetFirstChildControl()
        while child:
            walk_and_print(child, d + 1, max_depth)
            child = child.GetNextSiblingControl()
    except Exception:
        # Child enumeration can fail if UIA tree mutates during walk
        log.debug("Child control traversal failed", exc_info=True)


def scan_chrome_panes(vscode):
    """Collect all Chrome_RenderWidgetHostHWND panes."""
    panes = []

    def collect(ctrl, d=0):
        if d > 20:
            return
        try:
            if ctrl.ClassName == "Chrome_RenderWidgetHostHWND":
                panes.append(ctrl)
                return  # don't recurse into Chrome panes
        except Exception:
            # ClassName property may be unavailable on transient controls
            log.debug("ClassName check failed", exc_info=True)
        try:
            child = ctrl.GetFirstChildControl()
            while child:
                collect(child, d + 1)
                child = child.GetNextSiblingControl()
        except Exception:
            # Child enumeration can fail if UIA tree mutates
            log.debug("Chrome pane child traversal failed", exc_info=True)

    collect(vscode)
    return panes


def main():
    comtypes.CoInitializeEx()
    auto.uiautomation.SetGlobalSearchTimeout(2)

    print("Looking for VS Code window...")
    vscode = auto.WindowControl(searchDepth=1, SubName=VSCODE_TITLE)
    if not vscode.Exists(3):
        print("ERROR: VS Code window not found.")
        return
    print(f"Found: {vscode.Name!r}\n")

    print("=" * 60)
    print("SHALLOW WALK of VS Code window (depth 12, classes only):")
    print("=" * 60)
    walk_and_print(vscode, max_depth=12)

    print("\n" + "=" * 60)
    print("CHROME PANES found:")
    print("=" * 60)
    panes = scan_chrome_panes(vscode)
    print(f"  {len(panes)} Chrome pane(s) found")
    for i, pane in enumerate(panes):
        try:
            r = pane.BoundingRectangle
            print(f"  [{i}] rect=({r.left},{r.top},{r.right},{r.bottom})")
        except Exception:
            print(f"  [{i}] <no rect>")

    print("\n" + "=" * 60)
    print("DEEP WALK of each Chrome pane (depth 12) — looking for 'Allow this':")
    print("=" * 60)
    for i, pane in enumerate(panes):
        print(f"\n--- Chrome pane [{i}] ---")
        walk_and_print(pane, max_depth=12)

    print("\nDone. If you see '*** ALLOW THIS ***' above, detection should work.")
    print("If nothing found, the dialog may not have been visible during the scan.")


if __name__ == "__main__":
    # Keep scanning every 2s so you can trigger the dialog while it runs
    while True:
        print("\n" + "=" * 60)
        print(f"Scanning at {time.strftime('%H:%M:%S')} ...")
        print("=" * 60)
        try:
            main()
        except Exception as e:
            print(f"Error: {e}")
        print("\nWaiting 3s — trigger the permission dialog now...")
        time.sleep(3)
