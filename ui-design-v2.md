
# UI Design Spec v2 — YouTube Downloader (Windows desktop app)

Builds on `ui-design.md` (v1: single-window download form). v2 turns the app into a
tabbed CustomTkinter window with three sections — Скачать (Download), Очередь (Queue),
Статистика (Statistics) — plus a resizable window and an application icon. Palette,
fonts, corner radii and interaction states below are the SAME tokens as v1
(`ui-design.md` §1–2) — v2 only adds new tokens where the existing palette doesn't
cover a need (queue status colors, chart gridlines). Do not invent new base colors
outside what's listed here.

## 0. Palette additions (extends ui-design.md §1)

| Token          | Hex       | Usage |
|----------------|-----------|-------|
| `bg`           | `#0b0d10` | (from v1) window/tab background |
| `bg-raised`    | `#111418` | (from v1) cards, entries, table rows (odd) |
| `bg-raised-2`  | `#161a1f` | NEW — table row (even/alt), nested card-in-card, chart plot background |
| `ink`          | `#f2f1ec` | (from v1) primary text |
| `ink-dim`      | `#9a9d9f` | (from v1) secondary text, axis labels, gridline labels |
| `border`       | `#20242a` | (from v1) borders, chart gridlines |
| `accent`       | `#ff4d4d` | (from v1) primary actions, active tab indicator, progress fill, chart primary series |
| `accent-ink`   | `#0b0d10` | (from v1) text on accent fill |
| `success`      | `#28c840` | (from v1) "готово" status, success dot |
| `error`        | `#ff5f57` | (from v1) "ошибка" status, error dot |
| `warning`      | `#f5a623` | NEW — "скачивается"/"в очереди→активно" pulse accent, paused state |
| `queued`       | `#6b7280` | NEW — "в очереди" status dot/text (neutral gray, distinct from ink-dim so it reads as a state not disabled text) |
| `paused`       | `#9a9d9f` | NEW — "отменено"/paused status (reuses ink-dim, no new hex) |

Status color map (used everywhere a queue-item or history-row status appears):
- в очереди → `queued` (#6b7280)
- скачивается → `warning` (#f5a623)
- в очереди (merge/postprocess) → `warning` (#f5a623) — same as "скачивается", label changes to "обработка"
- готово → `success` (#28c840)
- ошибка → `error` (#ff5f57)
- отменено → `paused` (#9a9d9f)

## 1. Window & navigation

- Root window: `ctk.CTk()`, title `"YT Downloader"`, `fg_color="#0b0d10"`.
- Resizable: `self.resizable(True, True)`, `self.minsize(760, 480)`. Default startup size `900x600`.
- Layout: root frame splits into (top→bottom): brand+tab-bar row (fixed 48px), then a
  content frame that fills remaining space and swaps per-tab content (all three tab
  frames pre-built, only one `grid`/`pack`-ed at a time — instant switch, no rebuild).
- Tab bar sits directly under the brand dot+label from v1 §4.1, same row (brand left,
  tabs right, both vertically centered) — saves vertical space vs. a separate row:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ● YT Downloader        [ Скачать ] [ Очередь (2) ] [ Статистика ]        │ 48px, border-bottom 1px #20242a
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│                         (active tab content)                             │
│                                                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

- Tab buttons: `CTkButton` (segmented look), height 32, corner_radius=8, font Segoe UI
  13 (bold when active).
  - Inactive: `fg_color="transparent"`, `text_color="#9a9d9f"`, `hover_color="#161a1f"`.
  - Active: `fg_color="#161a1f"`, `text_color="#f2f1ec"`, plus a 2px accent underline —
    implement as a 2px-tall `CTkFrame(fg_color="#ff4d4d")` placed directly under the
    active tab button, width matched to button width, repositioned on tab switch.
  - Queue tab label includes a live count badge when non-empty: `"Очередь (2)"`; badge
    text only (no separate pill graphic, keep it simple) — omit `"(0)"` when empty →
    just `"Очередь"`.
- Настройки (Settings) tab: optional per spec, SKIP for v2 — only 3 tabs (Скачать,
  Очередь, Статистика). No settings tab is built.

## 2. Tab: Скачать (Download) — layout

Same as `ui-design.md` §3 (URL → Get info → title/formats preview → quality → save-to
→ progress → status/Download button), with ONE addition: point 2 below (per-format
preview before adding to queue). Reuse all v1 §4 component specs unchanged. The
"Download" button in v2 enqueues into the queue tab rather than blocking the UI single
file — clicking it adds a queue card and switches focus to the Очередь tab is NOT
automatic (stays on Скачать so user can paste another URL immediately — this is what
makes multi-add possible).

Padding/scroll: content frame uses 24px outer padding as in v1; this tab's content
does not scroll (fixed set of rows, fits in minsize height).

### 2.1 Format preview panel (NEW — appears after "Get info" succeeds, above Quality)

- Container: `CTkFrame(fg_color="#111418", corner_radius=8, border_width=1, border_color="#20242a")`, full width, internal padding 12px.
- Row 1: video title — `CTkLabel`, Segoe UI 13 bold, `text_color="#f2f1ec"`, wraplength 680, anchor "w".
- Row 2: duration — `CTkLabel`, Consolas 12, `text_color="#9a9d9f"`, text format `"Длительность: 00:12:34"`.
- Row 3: a scroll-free small table, one line per quality option, built as stacked
  `CTkFrame` rows (not a real ttk.Treeview — keep it CTk-native):
  `[ 2160p60 · видео+аудио      ~1.8 GB ]`
  `[ 1080p60 · видео+аудио      ~640 MB ]`
  `[ audio-only · mp3           ~9.4 MB ]`
  - Each row: `CTkFrame(fg_color="transparent")`, horizontal pack — left label (quality
    string, Segoe UI 12, `ink`), right label (size, Consolas 12, `ink-dim`), packed
    `side="left"`/`side="right"` with the row stretching full width.
  - Row height ~22px, no border between rows (rely on 4px vertical gap for separation).
  - Sizes come from format `filesize`/`filesize_approx` summed video+audio streams,
    prefixed with `~` since merged size is an estimate; if unknown show `"~ ?"`.
  - This table is informational only — selecting quality still happens via the
    existing Quality `CTkOptionMenu` below it (table does not duplicate the control,
    just previews sizes so the user can pick an informed quality before selecting it).

## 3. Tab: Очередь (Queue)

### 3.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  В очереди: 3 видео · всего 4.2 GB · 12 мин 40 сек                       │  <- summary bar, 40px, bg-raised, corner_radius=8, 12px padding
├──────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ [thumb] Название видео 1                          [⏸] [🗑]        │   │  <- queue card, ~88px tall
│  │  64x36   1080p60 · видео+аудио · 00:14:22                          │   │
│  │          ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░  62%  •  скачивается  •  3.4/5.6 MB   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ [thumb] Название видео 2                     [📁 Открыть]         │   │
│  │  64x36   720p · видео+аудио · 00:03:11                             │   │
│  │          готово · 118 MB                                           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ [thumb] Название видео 3                          [🔁] [🗑]        │   │
│  │  64x36   audio-only · mp3 · 00:05:45                                │   │
│  │          ошибка: сеть недоступна                                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┘
     ↑ scrollable list (CTkScrollableFrame), 12px vertical gap between cards
```

- Whole list lives in a `CTkScrollableFrame(fg_color="transparent")` filling the tab
  below the summary bar (summary bar fixed, list scrolls independently).
- Empty state (no items ever queued): centered `CTkLabel`, Segoe UI 13, `text_color="#9a9d9f"`, text `"Очередь пуста. Добавьте видео на вкладке «Скачать»."`, vertically centered in the scrollable frame area.

### 3.2 Summary bar

- `CTkFrame(fg_color="#111418", corner_radius=8)`, 40px tall, 12px horizontal padding, single `CTkLabel` left-anchored.
- Text template (Segoe UI 12, `text_color="#9a9d9f"`, numbers in `text_color="#f2f1ec"` if split into multiple labels — acceptable to keep as one label with plain text if splitting is impractical):
  `"В очереди: {N} видео · всего {X} · {H} ч {M} мин"` — omit hours segment when < 1h (`"{M} мин"` only). `{X}` uses the same GB/MB formatting rule as card sizes (§3.3).
  Counts only items with status in {queued, downloading, processing} — done/error/cancelled excluded from N/X/time (those live in Статистика's history table instead, see §4.4).

### 3.3 Queue card

- Container: `CTkFrame(fg_color="#111418", corner_radius=8, border_width=1, border_color="#20242a")`, full width, ~88px tall (grows to ~72px for done/error/cancelled cards which drop the progress row), internal padding 12px, `12px` vertical gap between cards in the scroll list.
- Left: thumbnail — `CTkImage` (64x36, 16:9) inside a `CTkLabel`, `corner_radius` on the frame only (CTkImage itself is a flat bitmap; acceptable per CTk limits). Real thumbnail via yt-dlp's `thumbnail` URL → downloaded once and cached to a temp/`.cache/thumbs/` dir → loaded via `PIL.Image` → `CTkImage(light_image=img, dark_image=img, size=(64,36))`. If thumbnail fetch fails or is still pending, show a placeholder: solid `#20242a` rounded rect with a centered `CTkLabel(text="▶", text_color="#9a9d9f")`.
- Top-right of card: action buttons, `CTkButton` 28x28, `corner_radius=6`, `fg_color="transparent"`, `border_width=1`, `border_color="#20242a"`, `text_color="#f2f1ec"`, `hover_color="#1a1e24"`, icon as unicode glyph (no image assets needed):
  - queued/downloading: `⏸` pause-toggle (becomes `▶` resume when paused) + `🗑` remove/cancel.
  - processing (merge step, still "скачивается" label per status map): same as downloading, pause disabled (grey out — merge step can't pause), only `🗑` (cancels).
  - готово: `📁 Открыть папку` (wider text button, not icon-only — `CTkButton(width=140, text="📁 Открыть папку")`) replaces the icon pair.
  - ошибка: `🔁 Повторить` (retry) + `🗑` remove.
  - отменено: `🗑` remove only (greyed `🔁 Повторить` also acceptable, optional — retry is the priority action, keep both if simple).
- Row 2 (under title): Consolas 12, `text_color="#9a9d9f"` — `"{quality} · {duration}"`, e.g. `"1080p60 · видео+аудио · 00:14:22"`.
- Row 3 (status row, layout differs by state):
  - downloading/processing: `CTkProgressBar` (same visual spec as v1 §4.6: track `#20242a`, fill `#ff4d4d` normal / `#f5a623` if state is "processing" i.e. merge step) height 6, corner_radius=4, inline before the text readout OR stacked directly above it (stacked preferred — progress bar full-width first, then one Consolas 12 line below: `"62% · скачивается · 3.4/5.6 MB · 4.1 MB/s · ETA 00:34"`, colored `ink-dim` except the percent number and status word which take the state's status color from the map in §0).
  - готово: single Consolas 12 line, `text_color="#28c840"`: `"готово · 118 MB"`.
  - ошибка: single Segoe UI 12 line, `text_color="#ff5f57"`: `"ошибка: {краткое сообщение}"`.
  - отменено: single Segoe UI 12 line, `text_color="#9a9d9f"`: `"отменено"`.
- Title row (row 1, next to thumbnail): `CTkLabel`, Segoe UI 13, `text_color="#f2f1ec"`, single line, `wraplength=0` (truncate — use `...` ellipsis manually if title exceeds available width, since CTk has no native ellipsis: truncate string by measured pixel width or a safe character cap like 70 chars + `"…"`).

### 3.4 Concurrency behaviour (visual only — logic is developer's to implement)

- Max 2 cards show status downloading/processing simultaneously (spec value: 1–2
  parallel per task body — use **2**). Any additional queued cards show status
  "в очереди" with `queued` color and no progress bar (row 3 = single line,
  `text_color="#6b7280"`, text `"в очереди"`) until a slot frees up.

## 4. Tab: Статистика (Statistics)

### 4.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [ Сегодня ]  [ 7 дней ]  [ 30 дней ]                                    │  <- period toggle, segmented buttons like tab bar, 32px
├───────────────────────┬───────────────────────┬──────────────────────────┤
│  Скачано видео        │  Всего данных         │  Общее время видео       │  <- 3 metric cards, equal width, 96px tall
│  128                  │  312.4 GB             │  46 ч 12 мин             │
├───────────────────────┴───────────────────────┴──────────────────────────┤
│  Активность по дням                                                      │  <- chart card, ~220px tall
│  [ ГБ ▾ / Кол-во видео ▾ ]  (small toggle top-right of card)             │
│                                                                            │
│    ▄▄     ▄▄▄▄  ▄  ▄▄▄▄▄▄  ▄▄  ▄▄▄▄▄▄▄▄  ▄▄▄  ▄▄▄▄▄▄  ▄▄▄▄  ▄▄  ▄▄▄▄▄▄▄▄  │  <- bar chart, tk.Canvas
│    ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──   │  <- gridlines + day labels
├──────────────────────────────────────────────────────────────────────────┤
│  История загрузок                                                        │  <- table card header
│  ┌────────────┬──────────────────────┬──────────┬─────────┬──────┬────┐ │
│  │ Дата       │ Название             │ Длит.    │ Размер  │ Кач. │Путь│ │
│  ├────────────┼──────────────────────┼──────────┼─────────┼──────┼────┤ │
│  │ 30.09 14:02│ Видео про котиков... │ 00:12:03 │ 118 MB  │1080p │📁  │ │  <- rows alternate bg-raised / bg-raised-2
│  │ ...        │ ...                  │ ...      │ ...     │ ...  │... │ │
│  └────────────┴──────────────────────┴──────────┴─────────┴──────┴────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

- Whole tab is a `CTkScrollableFrame(fg_color="transparent")` — total content taller
  than the window at minsize, so it must scroll (period toggle can stay inside the
  scroll area, no need to pin it — simplicity over a sticky header).

### 4.2 Period toggle

- Same segmented-button visual as the tab bar (§1): `CTkButton` height 32, corner_radius=8, inactive `fg_color="transparent"`/`text_color="#9a9d9f"`, active `fg_color="#161a1f"`/`text_color="#f2f1ec"` + 2px accent underline. Three options: `"Сегодня"`, `"7 дней"`, `"30 дней"`. Selecting one re-renders the 3 metric cards + chart (table always shows full history regardless of period — table has its own scroll, not period-filtered, since it's a log not a summary).

### 4.3 Metric cards

- Three `CTkFrame(fg_color="#111418", corner_radius=8, border_width=1, border_color="#20242a")` side by side (`grid` with `uniform` columns, 12px gap between), each 96px tall, internal padding 16px, vertical stack inside:
  - Label (top): Segoe UI 12, `text_color="#9a9d9f"` — `"Скачано видео"` / `"Всего данных"` / `"Общее время видео"`.
  - Value (below, larger): Segoe UI 26 bold, `text_color="#f2f1ec"` — number formatted per type (`"128"`, `"312.4 GB"`, `"46 ч 12 мин"`).
  - Size formatting rule (reused everywhere: cards, queue, history table): `< 1 GB` → `"{n} MB"` (0 decimals if ≥100, else 1 decimal); `≥ 1 GB` → `"{n} GB"` (1 decimal).

### 4.4 Chart — "Активность по дням"

- Card container: `CTkFrame(fg_color="#111418", corner_radius=8, border_width=1, border_color="#20242a")`, full width, ~220px tall, 16px padding.
- Header row: `CTkLabel(text="Активность по дням", font=Segoe UI 13 bold, text_color="#f2f1ec")` left, small metric toggle right — two tiny `CTkButton`s (or one `CTkSegmentedButton`-style pair) `"ГБ"` / `"Кол-во видео"`, same active/inactive coloring as period toggle but height 24, font 11. Default metric: `"ГБ"`.
- Chart itself: a plain `tkinter.Canvas` (NOT `CTkCanvas` — CTk has no canvas subclass, use raw `tk.Canvas` with `bg="#111418"`, `highlightthickness=0`), embedded via `.place()`/`.pack()` inside the card frame below the header, height ~160px, width = card width minus padding (redraw on `<Configure>` resize since window is resizable now).
- Data: last 30 calendar days always computed (chart itself doesn't change with the
  Сегодня/7 дней/30 дней period toggle — only the 3 metric cards + implicit table
  scroll position do; chart is always the fixed 30-day view since that's the only
  useful granularity for a bar chart in this space). If "Сегодня" or "7 дней" is
  selected, still draw all 30 days but you MAY visually dim (lower alpha via a
  lighter fill, e.g. `#2a2e35` instead of `#ff4d4d`) the bars outside the selected
  range to spotlight the active period — optional polish, not required for v2.
- Drawing (all via `canvas.create_*` primitives, redrawn fully on each data refresh /
  resize):
  - Y-axis gridlines: 4 horizontal lines (`canvas.create_line`, fill=`"#20242a"`,
    width=1) at 0%/33%/66%/100% of chart height, each with a small left-aligned value
    label (`canvas.create_text`, fill=`"#9a9d9f"`, font=("Consolas", 9)) showing the
    scale value for that gridline (e.g. `"0"`, `"1.2 GB"`, `"2.4 GB"`, `"3.6 GB"` or
    video-count equivalents when metric toggle = "Кол-во видео").
  - Bars: one per day, `canvas.create_rectangle`, fill=`"#ff4d4d"` (accent), no
    outline (`outline=""`), rounded look optional (canvas has no native rounded
    rect pre-8.6.10 reliably — plain rectangles are fine, matches "simple" bar chart
    ask), bar width = `(chart_width / 30) * 0.6` with `0.4` gap ratio between bars,
    bottom-anchored to the x-axis line.
  - X-axis: label every 5th day only (avoid clutter) as `"DD.MM"`, `canvas.create_text`,
    fill=`"#9a9d9f"`, font=("Consolas", 9), rotation not needed (short labels fit
    horizontally at this spacing).
  - Hover/tooltip: NOT required for v2 (keep canvas code simple — static redraw only,
    no `<Motion>` binding). Skip.
  - Empty/zero day: bar height 0 (just the baseline, no rectangle drawn) — do not draw
    a minimum-height stub, zero should visually read as zero.

### 4.5 History table

- Card container: same frame style as chart card, full width, header
  `CTkLabel(text="История загрузок", font=Segoe UI 13 bold, text_color="#f2f1ec")`,
  16px padding, height auto (grows with row count, whole tab already scrolls via the
  outer `CTkScrollableFrame` so this table does not need its own nested scrollbar —
  simplicity over a doubly-nested scroll region).
- Columns: Дата (`DD.MM HH:MM`), Название (truncated ~40 chars + `…`), Длительность
  (`ЧЧ:ММ:СС`), Размер (formatted per §4.3 rule), Качество (raw quality string, e.g.
  `"1080p60"`), Путь (a small `📁` icon-only button that opens the containing folder —
  same 28x28 transparent/border style as queue card action buttons).
- Built as stacked `CTkFrame` rows (NOT `ttk.Treeview` — keep fully CTk-native like the
  format preview table in §2.1), each row 32px tall:
  - Header row: `text_color="#9a9d9f"`, Segoe UI 12, `fg_color="#161a1f"` background,
    fixed (not part of the scroll — sits once above all data rows since the whole tab
    scrolls together, header just needs to visually read as a header, no sticky
    behavior needed).
  - Data rows: alternate `fg_color="#111418"` (odd) / `fg_color="#161a1f"` (even) —
    this reuses `bg-raised-2` from §0 — Segoe UI 12 (Consolas 12 for the Длительность/
    Размер numeric columns), `text_color="#f2f1ec"`.
  - Column widths (fixed, px, at 900px default window width — table area ≈ 850px after
    padding): Дата 110 · Название flexible/stretch (fills remaining space, min 200) ·
    Длительность 90 · Размер 90 · Качество 90 · Путь 44. Use `grid` with column
    `weight` only on Название so the table reflows sanely when the window is resized
    wider (all other columns fixed width).
  - Newest entries first (prepend, not append). No pagination for v2 — full history
    renders; acceptable since this is a personal-use utility app.
  - Empty state: single centered row, Segoe UI 12, `text_color="#9a9d9f"`,
    `"История пуста."`.

## 5. Application icon

### 5.1 Concept

A red rounded square (matches the app's `accent` red, `#ff4d4d`, and the brand-row
accent dot from v1) with a simple white downward arrow inside — the universal
"download" glyph, instantly recognizable at 16px, distinct silhouette from a generic
play button so it doesn't get confused with a media-player icon at a glance in the
taskbar. Flat design (no gradients/shadows/bevels) so it stays crisp when scaled down
to 16x16 — this is the single biggest risk for hand-authored icons, so the shape is
kept as two solid primitives (rounded square + arrow) with no fine detail that would
disappear at small sizes.

### 5.2 Geometry (fractions of icon size `S`, square canvas)

Background:
- Rounded square, filled `#ff4d4d`, inset `0.06·S` from each edge (so it doesn't touch
  the canvas edge — gives breathing room in the Windows taskbar/desktop icon frame),
  corner radius `0.18·S`.
  - i.e. for `S=256`: inset ≈15px, so square spans (15,15)→(241,241), corner radius ≈46px.

Arrow (drawn in white `#f2f1ec` — reuse `ink` token rather than pure `#ffffff` so it
matches the app's off-white text color exactly):
- A downward arrow = a vertical stem (rectangle) + a triangle head, both centered
  horizontally on the square, combined into one solid polygon (draw as a single
  `ImageDraw.polygon` for a clean silhouette — no separate overlapping shapes that
  could show seams when anti-aliased).
- Define in fractions of `S`, all coordinates relative to icon top-left (0,0):
  - Stem: width `0.16·S`, from top `y=0.28·S` to `y=0.56·S`, horizontally centered
    (`x_center = 0.5·S`, so stem spans `x = 0.42·S` to `0.58·S`).
  - Arrowhead: isosceles triangle, apex pointing down at `y=0.74·S`, base at
    `y=0.56·S` spanning `x=0.32·S` to `0.68·S` (wider than the stem so it reads as a
    clear arrowhead, not just a thicker stem-end).
  - Combined polygon points (clockwise, in `S`-fractions, multiply by `S` and round to
    int when rendering at a given size):
    `(0.42,0.28) (0.58,0.28) (0.58,0.56) (0.68,0.56) (0.50,0.74) (0.32,0.56) (0.42,0.56)`
  - This traces: down the right side of the stem, out to the wide right base of the
    head, down to the apex, back up to the wide left base of the head, up the left
    side of the stem, closing the polygon.
- Optional (skip if it adds fragility at small sizes): a thin horizontal white
  baseline under the arrow (`y=0.80·S` to `0.82·S`, `x=0.30·S` to `0.70·S`, same
  white) representing a "tray"/"shelf" the download lands on — a common download-icon
  convention. Include ONLY at sizes ≥48px (omit entirely below that — it would be a
  1px sliver at 16/24/32 and hurt legibility); simplest correct approach is to just
  never draw it (arrow alone is a complete, recognizable download glyph) — this
  sub-bullet is optional polish, the required shape is the square + arrow above.

### 5.3 Rendering (Pillow ImageDraw, for the developer building `assets/icon.ico`)

```python
from PIL import Image, ImageDraw

BG = "#ff4d4d"
FG = "#f2f1ec"

def render_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inset = round(size * 0.06)
    radius = round(size * 0.18)
    d.rounded_rectangle([inset, inset, size - inset, size - inset], radius=radius, fill=BG)
    pts = [(0.42,0.28),(0.58,0.28),(0.58,0.56),(0.68,0.56),(0.50,0.74),(0.32,0.56),(0.42,0.56)]
    d.polygon([(x * size, y * size) for x, y in pts], fill=FG)
    return img

sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [render_icon(s) for s in sizes]
imgs[-1].save("assets/icon.ico", sizes=[(s, s) for s in sizes])  # multi-res .ico
```

- Render each size independently from the fractional geometry (don't just resize the
  256px bitmap down to 16px with a filter — re-rendering at each target size from the
  vector-ish fractions keeps edges crisper at small sizes, since `rounded_rectangle`'s
  radius and the polygon both scale cleanly).
- Save as a single multi-resolution `assets/icon.ico` containing all 7 sizes (Pillow's
  `.ico` writer supports the `sizes=` kwarg to bundle multiple resolutions in one file,
  which is what Windows expects for exe/shortcut/taskbar icons at different DPI/zoom
  levels).
- Use in `build.spec` (PyInstaller) via `icon="assets/icon.ico"`, and in the window
  itself via `self.iconbitmap("assets/icon.ico")` (Windows-only API, guard with
  `try/except` or `sys.platform == "win32"` check since `iconbitmap` with a `.ico` arg
  is Windows-specific — CTk root is a `tk.Tk` subclass so this works unchanged from
  v1's plain-tkinter version).

### 5.4 `assets/icon.svg` (companion vector, same geometry)

Same shape, hand-written SVG using the same fractional geometry scaled to a 256x256
viewBox, so it stays byte-for-byte consistent with the Pillow renderer's proportions.
Kept alongside the `.ico` per the task's "also save as assets/icon.svg" requirement —
useful for docs/README/favicon reuse without regenerating from Python. See
`assets/icon.svg` in this same folder (already written as part of this spec).

## 6. Component/functionality mapping notes (v2 additions only — v1 §6 mapping still applies to the Скачать tab)

| New v2 element                     | Widget |
|-------------------------------------|--------|
| Tab bar / period toggle / chart metric toggle | `CTkButton` group (manual segmented — no native `CTkSegmentedButton` state styling assumed beyond what's specced above; use `CTkSegmentedButton` if the installed CTk version supports the exact color hooks needed, otherwise the manual button-group approach above is the fallback and is what this spec assumes throughout) |
| Queue list | `CTkScrollableFrame` + per-item `CTkFrame` cards |
| Queue thumbnail | `CTkImage` from a cached PIL image (fetched via yt-dlp `thumbnail` field) |
| Statistics chart | raw `tk.Canvas` (not CTk — no CTk canvas widget exists), manual `create_rectangle`/`create_line`/`create_text` |
| History table | stacked `CTkFrame` rows in `grid`, NOT `ttk.Treeview` (stay CTk-native for consistent dark styling — ttk.Treeview's dark-mode theming is unreliable across Windows versions) |
| App icon | `assets/icon.ico` (multi-res) via `iconbitmap()` + `assets/icon.svg` vector companion |

## 7. Texts (Russian, complete list for the developer to use verbatim)

Tabs: `Скачать` · `Очередь` (with optional `(N)` count) · `Статистика`

Download tab (unchanged from v1 aside from reuse): `Get info` button stays as-is per
v1 spec if already implemented in Russian elsewhere — for v2 consistency, if the
developer is localizing fully, use `Получить инфо` for the button and `Скачать` for
the primary download/enqueue button, `Обзор…` for Browse; status line idle text
`Вставьте ссылку на YouTube-видео и нажмите «Получить инфо»`.

Format preview: `Длительность: {ЧЧ:ММ:СС}` · size cells `~{X}` (formatted per §4.3).

Queue summary: `В очереди: {N} видео · всего {X} · {H} ч {M} мин` (or `{M} мин` if <1h).

Queue statuses: `в очереди` · `скачивается` · `обработка` · `готово` · `ошибка` ·
`отменено`.

Queue card actions: `📁 Открыть папку` · `🔁 Повторить` · pause/resume icons only (no
text label needed, ⏸/▶ are self-explanatory) · 🗑 remove (icon only).

Queue empty state: `Очередь пуста. Добавьте видео на вкладке «Скачать».`

Statistics period toggle: `Сегодня` · `7 дней` · `30 дней`.

Statistics metric cards: `Скачано видео` · `Всего данных` · `Общее время видео`.

Statistics chart: `Активность по дням` · chart metric toggle `ГБ` / `Кол-во видео`.

Statistics table: header `История загрузок`; columns `Дата` · `Название` ·
`Длительность` · `Размер` · `Качество` · `Путь`; empty state `История пуста.`

Errors (reuse v1 pattern, `ошибка: {краткое сообщение}`), e.g. `ошибка: сеть
недоступна`, `ошибка: видео недоступно`, `ошибка: не удалось объединить дорожки`.
