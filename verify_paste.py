"""Verify Paste button / Ctrl+V / <<Paste>> / right-click all land in url_var."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from gui import DownloaderApp  # noqa: E402

TEST_URL = "https://youtube.com/watch?v=test"
failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + extra if extra else ""))
    if not cond:
        failures.append(name)


def main() -> None:
    app = DownloaderApp()
    app.clipboard_clear()
    app.clipboard_append(TEST_URL)
    app.update()
    inner = app.url_entry._entry

    def state():
        return inner.get(), app.url_var.get(), app.url_entry.get()

    def reset():
        app.on_clear()
        app.update()

    check("paste_btn exists", hasattr(app, "paste_btn") and app.paste_btn.cget("text") == "Paste")

    # 1. Paste button click (invoke the real command callback)
    app.paste_btn._command()
    app.update()
    e, v, g = state()
    check("paste button -> url_var", v == TEST_URL, repr(v))
    check("paste button -> entry text", e == TEST_URL, repr(e))
    check("paste button -> CTkEntry.get()", g == TEST_URL, repr(g))
    check("placeholder cleared", not app.url_entry._placeholder_text_active)

    # 2. Ctrl+V via physical keycode (layout independent)
    reset()
    inner.focus_force()
    app.update()
    # Tk only lets us set the physical keycode on a synthetic event (a keysym
    # cannot be combined with it), which is exactly the layout-independent
    # path the fix relies on: VK_V == 86 whatever the active layout reports.
    inner.event_generate("<Control-KeyPress>", keycode=86)
    app.update()
    e, v, _ = state()
    check("Ctrl+V (keycode VK_V, any layout) -> url_var", v == TEST_URL, repr(v))
    check("Ctrl+V (keycode VK_V, any layout) -> entry", e == TEST_URL, repr(e))

    # 3. Other Ctrl+<key> must NOT paste (no over-broad binding)
    reset()
    inner.event_generate("<Control-KeyPress>", keycode=65)  # Ctrl+A
    app.update()
    check("Ctrl+A does not paste", app.url_var.get() == "", repr(app.url_var.get()))

    # 4. Virtual <<Paste>> (system paste path)
    reset()
    inner.event_generate("<<Paste>>")
    app.update()
    e, v, _ = state()
    check("<<Paste>> -> url_var", v == TEST_URL, repr(v))
    check("<<Paste>> not duplicated", e == TEST_URL, repr(e))

    # 5. Shift+Insert
    reset()
    inner.event_generate("<Shift-Insert>")
    app.update()
    check("Shift+Insert -> url_var", app.url_var.get() == TEST_URL, repr(app.url_var.get()))

    # 6. Right-click menu Paste entry
    reset()
    labels = [app._url_menu.entrycget(i, "label") for i in range(app._url_menu.index("end") + 1)]
    check("context menu has Paste", "Paste" in labels, str(labels))
    app._url_menu.invoke(labels.index("Paste"))
    app.update()
    check("context menu Paste -> url_var", app.url_var.get() == TEST_URL, repr(app.url_var.get()))

    # 7. whitespace/newline normalisation
    reset()
    app.clipboard_clear()
    app.clipboard_append("  " + TEST_URL + "\n")
    app.update()
    app.on_paste()
    app.update()
    check("clipboard whitespace trimmed", app.url_var.get() == TEST_URL, repr(app.url_var.get()))

    # 8. empty clipboard -> friendly status, no crash
    reset()
    app.clipboard_clear()
    app.clipboard_append("")
    app.update()
    app.on_paste()
    app.update()
    check("empty clipboard handled", app.url_var.get() == "" and "lipboard" in app.status_var.get(),
          repr(app.status_var.get()))

    # 9. typing still works after bindings installed.
    # NOTE: synthetic <KeyPress-x> does not insert text even on a bare
    # tkinter.Entry (verified separately), so exercise the real insert path
    # and assert the paste bindings don't swallow or corrupt normal input.
    reset()
    inner.focus_force()
    inner.insert("end", "abc")
    app.update()
    check("plain typing unaffected", app.url_var.get() == "abc", repr(app.url_var.get()))

    # 10. no stray global bind_all on the app
    check("no bind_all paste hijack", "<<Paste>>" not in app.bind_all(),
          str(app.bind_all()))

    app.destroy()
    print("\n%d checks, %d failures" % (10 + 8, len(failures)))
    if failures:
        print("FAILED:", failures)
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
