"""
probe_uia.py — Targeted scan of the Claude Code chat webview (v3)

Uses uiautomation built-in search to find the webview, then walks
deep inside it to read actual chat message text.
"""

import logging

import uiautomation as auto

log = logging.getLogger(__name__)

VSCODE_TITLE = "Visual Studio Code"

auto.uiautomation.SetGlobalSearchTimeout(5)


def walk_deep(control, depth=0, max_depth=25, results=None):
    if results is None:
        results = []
    if depth > max_depth:
        return results
    try:
        name = (control.Name or "").strip()
        ctype = control.ControlTypeName or ""

        # Also try TextPattern for richer text
        text = name
        try:
            tp = control.GetTextPattern()
            raw = tp.DocumentRange.GetText(-1).strip()
            if len(raw) > len(text):
                text = raw
        except Exception:
            # TextPattern not supported on all control types — debug only
            log.debug("TextPattern extraction failed", exc_info=True)

        if len(text) >= 6:
            results.append((depth, ctype, text))
    except Exception:
        # Control may be stale or inaccessible mid-traversal
        log.debug("Control property read failed", exc_info=True)

    try:
        child = control.GetFirstChildControl()
        while child:
            walk_deep(child, depth + 1, max_depth, results)
            child = child.GetNextSiblingControl()
    except Exception:
        # Child enumeration can fail if the UIA tree mutates during walk
        log.debug("Child control traversal failed", exc_info=True)

    return results


def print_results(results, label=""):
    if label:
        print(f"\n── {label} {'─' * (60 - len(label))}")
    if not results:
        print("  (no text found)")
        return
    print(f"{'DEPTH':<6} {'TYPE':<22} TEXT")
    print("-" * 85)
    for depth, ctype, text in results:
        display = text.replace("\n", " ").strip()
        if len(display) > 68:
            display = display[:65] + "..."
        print(f"{depth:<6} {ctype:<22} {'  ' * depth}{display}")
    print(f"\n  {len(results)} elements found.")


def main():
    print("Searching for VS Code window...")
    vscode = auto.WindowControl(searchDepth=1, SubName=VSCODE_TITLE)
    if not vscode.Exists(5):
        print("VS Code not found.")
        return
    print(f"Found: {vscode.Name}\n")

    # ── Strategy 1: find Chrome render widget, then search for DocumentControls ──
    print("Strategy 1: Chrome render widget → DocumentControls...")
    chrome = vscode.PaneControl(searchDepth=12, ClassName="Chrome_RenderWidgetHostHWND")
    if chrome.Exists(3):
        print("  Chrome render widget found.\n")

        # Find all DocumentControls inside Chrome widget
        docs = []

        def collect_docs(ctrl, d=0):
            if d > 15:
                return
            try:
                if ctrl.ControlTypeName == "DocumentControl":
                    docs.append((d, ctrl))
            except Exception:
                # ControlTypeName read may fail on transient controls
                log.debug("ControlTypeName check failed", exc_info=True)
            try:
                child = ctrl.GetFirstChildControl()
                while child:
                    collect_docs(child, d + 1)
                    child = child.GetNextSiblingControl()
            except Exception:
                # Child enumeration can fail if UIA tree mutates
                log.debug("collect_docs child traversal failed", exc_info=True)

        collect_docs(chrome)
        print(f"  Found {len(docs)} DocumentControl(s) inside Chrome widget:")
        for d, doc in docs:
            try:
                print(f"    depth={d}  name={doc.Name[:80]}")
            except Exception:
                print(f"    depth={d}  name=(unreadable)")

        # Walk the deepest / most likely chat DocumentControl
        if docs:
            # Pick the one with "vscode-webview" in name, or the deepest one
            chat_doc = None
            for d, doc in docs:
                try:
                    if "vscode-webview" in (doc.Name or ""):
                        chat_doc = doc
                        break
                except Exception:
                    # Name property may be unavailable on stale controls
                    log.debug("vscode-webview name check failed", exc_info=True)
            if not chat_doc:
                chat_doc = docs[-1][1]

            print(
                f"\n  Walking into: {chat_doc.Name[:60] if chat_doc.Name else '(unnamed)'}..."
            )
            results = walk_deep(chat_doc, max_depth=20)
            print_results(results, "Chat webview content")
    else:
        print("  Chrome render widget not found at depth 12.")

    # ── Strategy 2: built-in searchDepth on the window ──────────────────────────
    print("\nStrategy 2: built-in DocumentControl search on VS Code window...")
    doc = vscode.DocumentControl(searchDepth=20)
    if doc.Exists(3):
        print(f"  First DocumentControl found: {doc.Name[:80]}")
        results = walk_deep(doc, max_depth=20)
        print_results(results, "First DocumentControl content")
    else:
        print("  No DocumentControl found via built-in search.")


if __name__ == "__main__":
    main()
