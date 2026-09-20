# UI Design Spec — YouTube Downloader (Windows desktop app)

Reference: `index.html` (marketing page for this project) defines the visual language.
This spec translates that language into a desktop app built with **CustomTkinter**
(dark mode, rounded corners, system font). This is NOT a web layout — it's a single
fixed-ish desktop window, laid out top-to-bottom in one column.

## 1. Palette (hex, exact — reuse index.html tokens)

| Token         | Hex       | Usage |
|---------------|-----------|-------|
| `bg`          | `#0b0d10` | Window background (root, main frame) |
| `bg-raised`   | `#111418` | Cards / grouped panels / entry fields / terminal-style output block |
| `ink`         | `#f2f1ec` | Primary text (labels, values, title) |
| `ink-dim`     | `#9a9d9f` | Secondary text (hints, status line when idle, placeholder text) |
| `border`      | `#20242a` | Borders/outlines on inputs, cards, separators |
| `accent`      | `#ff4d4d` | Primary button fill, focus ring, progress bar fill, links/kicker text, error accent |
| `accent-ink`  | `#0b0d10` | Text color drawn on top of `accent` fill (e.g. text on the red Download button) |
| `success`     | `#28c840` | Optional: "done" status text / success dot (borrowed from terminal traffic-light in index.html) |
| `error`       | `#ff5f57` | Error status text / error state border (borrowed from terminal traffic-light) |

CustomTkinter setup:
```python
import customtkinter as ctk
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")  # overridden per-widget with explicit hex below — theme file only sets base shape
```
All actual colors are passed explicitly per-widget (`fg_color=`, `text_color=`, `border_color=`) using the hex table above — do not rely on the built-in blue theme's accent.

## 2. Typography

- Font family: `"Segoe UI"` (system default on Windows, no bundling needed). CustomTkinter's `CTkFont` accepts it directly: `ctk.CTkFont(family="Segoe UI", size=13)`.
- Monospace accents (URL echo, file sizes, speed/ETA, quality tags) use `"Consolas"` (also preinstalled on Windows) at size 12 — mirrors the `--mono` token in index.html used for the kicker, table tags, terminal body.
- Sizes:
  - App title / header brand text: Segoe UI, size 15, weight bold, color `ink`
  - Section labels ("Video URL", "Quality", "Save to"): Segoe UI, size 12, weight normal, color `ink-dim`
  - Field values / entry text: Segoe UI, size 13, color `ink`
  - Video title (after Get Info): Segoe UI, size 13, weight bold, color `ink`, wraplength ~520px
  - Status line: Segoe UI, size 12, color `ink-dim` (normal) / `error` (on error) / `success` (on done)
  - Monospace progress readout (percent / speed / ETA): Consolas, size 12, color `ink-dim`, with the percentage number itself in `accent`
  - Button label: Segoe UI, size 13, weight bold

## 3. Window & layout

- Window size: 760x460, `resizable(False, False)` — this is a small utility app, not a responsive page. `minsize` not needed if resizing is disabled.
- Window `fg_color` = `bg` (`#0b0d10`). Title bar stays native Windows chrome (no custom titlebar needed — CTk doesn't require it and it'd add scope).
- Single root `CTkFrame` (`fg_color="#0b0d10"`) filling the window with 24px outer padding on all sides.
- Vertical stack, top to bottom, each block separated by 14px vertical gap:

```
┌──────────────────────────────────────────────────────────────────┐
│  ●  YT Downloader                                                 │  <- brand row, 12px accent dot + bold label
├──────────────────────────────────────────────────────────────────┤
│  VIDEO URL                                                        │  <- section label, ink-dim, 11px uppercase-ish (Segoe UI, letter-spaced via padding not real tracking)
│  [ https://youtube.com/watch?v=...          ] [ Get info ]        │  <- entry (raised bg) + primary accent button, same row
├──────────────────────────────────────────────────────────────────┤
│  Video Title Goes Here (wraps to two lines if long)                │  <- appears only after successful fetch, ink, bold
├──────────────────────────────────────────────────────────────────┤
│  QUALITY                                                           │
│  [ 2160p60 · video+audio merged  ▾ ]                                │  <- CTkOptionMenu / CTkComboBox, raised bg, disabled until formats loaded
├──────────────────────────────────────────────────────────────────┤
│  SAVE TO                                                            │
│  [ C:\Users\you\Downloads                    ] [ Browse… ]           │  <- readonly entry + secondary (outline) button
├──────────────────────────────────────────────────────────────────┤
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░  71%                    │  <- CTkProgressBar, accent fill on border-colored track
│  71.0%   18.4 MB/s        ETA 00:07                                 │  <- monospace status row, split left/right (pack with side=left/right)
├──────────────────────────────────────────────────────────────────┤
│  Status message text (idle / fetching / downloading / done / error)│  <- ink-dim normal, error/success colored on those states
│                                                    [  Download  ]   │  <- primary accent button, right-aligned, disabled until quality chosen
└──────────────────────────────────────────────────────────────────┘
```

Row-by-row spacing/margins:
- Brand row: 0 top margin, 10px bottom margin, bottom border via a 1px `CTkFrame` (`fg_color="#20242a"`, height=1) spanning full width, 14px margin below the border before next block.
- Label→field gap: 6px.
- Between logical blocks (URL block, quality block, save-to block, progress block, status/download row): 16px.
- Entry/button height: 36px consistently across all inputs and buttons for visual rhythm.
- Corner radius: 8px on all inputs, buttons, and the progress bar track (`corner_radius=8`). This matches index.html's `border-radius:8-12px` on buttons/cards — "rounded corners, no default gray tkinter look."

## 4. Components (CustomTkinter widget + spec)

### 4.1 Brand row
- `CTkFrame` fg_color=transparent, horizontal pack.
- Left: a small 10x10 canvas/oval or a `CTkLabel` with a "●" glyph, `text_color=accent`. Followed by 8px gap, then `CTkLabel(text="YT Downloader", font=Segoe UI 15 bold, text_color=ink)`.
- No right-side nav needed (this isn't a webpage) — brand row is just identity.

### 4.2 URL entry + Get Info button
- `CTkEntry`: `fg_color="#111418"`, `border_color="#20242a"`, `border_width=1`, `text_color="#f2f1ec"`, `placeholder_text="Paste a YouTube video URL…"`, `placeholder_text_color="#9a9d9f"`, height=36, corner_radius=8, font Segoe UI 13.
  - Focus state: `border_color` changes to `accent` (`#ff4d4d`) — bind `<FocusIn>`/`<FocusOut>` to swap `border_color` since CTkEntry doesn't do this automatically.
- `CTkButton` ("Get info"): `fg_color="#ff4d4d"`, `text_color="#0b0d10"`, `hover_color="#e34343"` (slightly darker red for hover), height=36, corner_radius=8, font Segoe UI 13 bold, `command=on_fetch`.
  - Disabled state (while busy or on subsequent view before any URL typed is fine as normal — disabled specifically *during* fetch): `fg_color="#3a2626"`, `text_color="#6b6f71"` (CTkButton `state="disabled"` — set these as `fg_color`/`text_color` overrides too since CTk's disabled dimming can be inconsistent across versions).

### 4.3 Video title label
- `CTkLabel`, empty string until formats are fetched. `text_color="#f2f1ec"`, font Segoe UI 13 bold, `wraplength=680`, `justify="left"`, anchor `"w"`.

### 4.4 Quality selector
- `CTkOptionMenu` (preferred over combobox for the closed dark aesthetic; dropdown menu itself should also be styled): `fg_color="#111418"`, `button_color="#111418"`, `button_hover_color="#1a1e24"`, `text_color="#f2f1ec"`, `dropdown_fg_color="#111418"`, `dropdown_text_color="#f2f1ec"`, `dropdown_hover_color="#20242a"`, height=36, corner_radius=8, font Segoe UI 13.
  - Disabled state (before Get Info succeeds): `state="disabled"`, `fg_color="#111418"`, `text_color="#5c5f61"`, placeholder value `"—"`.
  - Values list: same strings currently produced by `FormatInfo.note` (e.g. "2160p60 · video+audio merged") — logic untouched, only the widget class/styling changes.

### 4.5 Save-to row
- `CTkEntry` (readonly): same visual spec as URL entry but `state="readonly"`, showing `self.output_dir`.
- `CTkButton` ("Browse…"): secondary/outline style — `fg_color="transparent"`, `border_width=1`, `border_color="#20242a"`, `text_color="#f2f1ec"`, `hover_color="#161a1f"`, height=36, corner_radius=8, font Segoe UI 13. Matches `.btn-secondary` in index.html.

### 4.6 Progress bar + readout
- `CTkProgressBar`: `fg_color="#20242a"` (track), `progress_color="#ff4d4d"` (fill), height=6, corner_radius=4, `mode="determinate"`. Value is 0.0–1.0 (CTk uses fractional, not 0-100 — convert from the existing percent math).
- Below it, a horizontal row with two `CTkLabel`s pinned left and right (pack `side="left"` / `side="right"` in a full-width sub-frame): left = `"71.0%   18.4 MB/s"`, right = `"ETA 00:07"`. Font Consolas 12, `text_color="#9a9d9f"`; the percentage substring itself can be a separate label with `text_color="#ff4d4d"` if easy to split, otherwise dim color for the whole line is acceptable.

### 4.7 Status line
- `CTkLabel`, font Segoe UI 12, anchor `"w"`, `wraplength=520`.
- Idle: `text_color="#9a9d9f"`, text = `"Paste a YouTube URL and press \"Get info\"."`
- Busy/info: `text_color="#9a9d9f"`
- Success ("Saved to: ..."): `text_color="#28c840"`
- Error ("Error — see dialog."): `text_color="#ff5f57"`

### 4.8 Download button
- `CTkButton`: identical visual spec to "Get info" (`fg_color="#ff4d4d"`, `text_color="#0b0d10"`, `hover_color="#e34343"`, height=36, corner_radius=8, font Segoe UI 13 bold), right-aligned in its row (pack/grid with `sticky="e"`).
- Disabled state (no formats loaded yet, or busy downloading): `fg_color="#3a2626"`, `text_color="#6b6f71"`.

### 4.9 Error/info dialogs
- Keep `tkinter.messagebox` calls (CustomTkinter doesn't replace these) — acceptable to leave native Windows dialog styling for `showerror`/`showinfo`, since restyling modal dialogs is out of scope and index.html has no equivalent element to match against. This is the one place default OS chrome is fine.

## 5. Interactive states summary

| Component       | Default                          | Hover                             | Disabled                          | Focus/Active                  | Error |
|------------------|-----------------------------------|-------------------------------------|--------------------------------------|----------------------------------|-------|
| URL entry        | border `#20242a`, bg `#111418`    | —                                   | —                                    | border `#ff4d4d`                | — |
| Get info / Download button | bg `#ff4d4d`, text `#0b0d10` | bg `#e34343`                      | bg `#3a2626`, text `#6b6f71`         | — (no separate pressed state needed) | — |
| Browse button (outline) | transparent, border `#20242a`, text `#f2f1ec` | bg `#161a1f` | — | — | — |
| Quality dropdown | bg `#111418`, text `#f2f1ec`      | button bg `#1a1e24`                | bg `#111418`, text `#5c5f61`, value `"—"` | dropdown open: items hover `#20242a` | — |
| Progress bar     | track `#20242a`, fill `#ff4d4d`   | —                                   | value stuck at 0 when idle           | —                                | — |
| Status label     | text `#9a9d9f`                    | —                                   | —                                    | —                                | text `#ff5f57` |

## 6. Component/functionality mapping (do not change logic, only widget class)

| Current (tkinter/ttk)                        | New (CustomTkinter)          |
|-----------------------------------------------|-------------------------------|
| `tk.Tk` root                                  | `ctk.CTk`, `fg_color="#0b0d10"` |
| `ttk.Entry` (URL)                             | `ctk.CTkEntry` |
| `ttk.Button` "Get info"                       | `ctk.CTkButton` (primary style) |
| `ttk.Label` title_var                         | `ctk.CTkLabel` |
| `ttk.Combobox` format_combo                   | `ctk.CTkOptionMenu` (or `CTkComboBox` if editable text is later needed — plain menu is enough since it's read-only today) |
| `ttk.Entry` dir_var (readonly)                | `ctk.CTkEntry` (`state="readonly"`) |
| `ttk.Button` "Browse…"                        | `ctk.CTkButton` (secondary/outline style) |
| `ttk.Progressbar`                              | `ctk.CTkProgressBar` (note: 0.0–1.0 scale, not 0–100) |
| `ttk.Label` progress_var                       | `ctk.CTkLabel` (Consolas font) |
| `ttk.Button` "Download"                        | `ctk.CTkButton` (primary style) |
| `ttk.Label` status_var                         | `ctk.CTkLabel` |
| `messagebox.showerror/showinfo`                | unchanged (native dialogs) |

All `StringVar`/`queue`/threading logic in `gui.py` stays as-is; only widget construction and styling change. `self.geometry("720x330")` becomes `760x460` with `resizable(False, False)`.

## 7. Assets

None required — no icons/images. The only visual flourish is the accent-colored dot in the brand row (drawable as a `CTkLabel(text="●")` in accent color, no image asset needed) and CustomTkinter's built-in rounded-rect rendering handles all "shape" work without extra files.
