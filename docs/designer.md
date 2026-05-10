# GUI Designer

IDOL includes a full **VB6-style drag-and-drop GUI builder** for Tkinter applications — the only Python IDE with a visual form designer built in.

> **Activation:** The Designer only appears for **Tkinter GUI App** projects. Create one with `File → New Project…` and select **Tkinter GUI App** — the wizard scaffolds `Form1.py`, `Form1.form.json`, and a `main.py` entry point, then drops you straight into the canvas.

## Layout

```
┌──────────────────┬──────────────────────────┬──────────────────┐
│ FORMS        [+] │  [Editor]  [Designer]    │ Properties       │
│  ⬜ Form1        │  Toolbar (align/snap)    │ Panel            │
│    ⧉ Dialog1     │  Canvas (dotted grid)    │                  │
│    ⧉ Dialog2     │                          │ Name: btn1       │
│  Unlinked        │  ┌────────────────────┐  │ Text: Click Me   │
│    ⧉ Dialog3     │  │ Form1              │  │ Width: 90        │
│ ──────────────   │  │  [Click Me]        │  │ ── Events ──     │
│ Widget Palette   │  └────────────────────┘  │ Click: [stub ▼]  │
│ [Button] [Label] │                          │                  │
└──────────────────┴──────────────────────────┴──────────────────┘
```

Entering Designer mode swaps the File Explorer out and the Widget Palette in — same left-panel slot, no floating windows. The left panel is split: the **FORMS tree** sits at the top, and the **Widget Palette** fills the rest. Exiting Designer restores the Explorer.

## Canvas

- **Dotted-grid design surface** — form rendered at real size with a simulated title bar and drop shadow
- **Widgets render realistically** — relief styles (raised, sunken, groove, ridge, solid, flat), disabled state, password dots, progress bars, checked checkboxes, and more; changing the `relief` property in the Properties panel updates the canvas immediately
- **Click to select** — blue dashed border + 8 white resize handles appear on the selected widget
- **Click the title bar** — selects the form and reveals its resize handles (dashed border + 8 corner/edge handles)
- **Drag to move** — repositions with 8px snap-to-grid; hold **Shift** while dragging for 1px precision
- **Drag a handle to resize** — snapped to the same 8px grid; hold **Shift** for 1px precision
- **Multi-select** — rubber-band drag to select multiple widgets; Ctrl+Click to toggle individual widgets; drag the group to move all at once
- **Primary vs secondary selection** — the last-clicked widget is the primary (amber border + full resize handles); all others are secondary (blue border only); resize dragging on any handle propagates the delta to all selected widgets
- **Copy / Paste** — Ctrl+C / Ctrl+V to duplicate; right-click context menu with Copy, Paste, Delete, Bring to Front, Send to Back
- **Arrow-key nudge** — 1px precision positioning with arrow keys
- **Z-order** — Bring to Front / Send to Back preserved on every mutation
- **Menu bar strip** — live menu bar rendered below the title bar from your menu items; clicking a top-level name opens a native dropdown; clicking a command or check/radio item with a handler navigates to that handler in the editor
- **Canvas scrollbars** — the canvas has horizontal and vertical scrollbars with mousewheel support; the form recenters automatically after a resize drag

## Widget Palette

14 widget types in a scrollable toolbox with canvas-drawn mini-previews:

Button, Label, Entry, Text, Checkbutton, Radiobutton, Combobox, Listbox, Frame, LabelFrame, Scale, Spinbox, Progressbar, Separator

**Placement modes:**
- **Click** — arms the crosshair tool; click anywhere on the canvas to drop at default size
- **Click-and-drag on canvas** — after arming, drag out a bounding box on the canvas; the widget is placed at exactly the drawn size (grid-snapped, 16px minimum); hold **Shift** while dragging to place at exact pixel size (1px minimum); a plain click without dragging still drops at default size
- **Drag from palette to canvas** — drag a palette item directly onto the canvas; a ghost label follows the cursor; releasing over the canvas drops the widget at default size at that position; releasing outside the canvas cancels
- **Double-click** — places the widget at the centre of the form immediately, without needing a canvas click

**Multi-placement mode** — a single click on a palette item keeps the tool armed after each drop. Every subsequent canvas click places another widget of the same type. De-arm by pressing Escape, clicking outside the canvas, or selecting the Pointer tool.

**Smart placement cursor** — while a palette tool is armed, the cursor changes based on what's under it:
- **Crosshair** over empty form area — click will place a new widget
- **Arrow** over an unselected widget — click selects it and de-arms the tool
- **Fleur (move)** over a selected widget — drag moves it immediately; click selects and de-arms

## Toolbar

A horizontal strip above the canvas with alignment, snap, and history controls.

**Left cluster — Alignment** (requires ≥2 selected):
- Align Left, Right, Top, Bottom, Center Horizontally, Center Vertically

**Center cluster — Distribution** (requires ≥3 selected):
- Distribute Equal Horizontal / Vertical spacing — grid-aware: clusters widgets into rows/columns and assigns uniform positions

**Center cluster — Sizing** (requires ≥2 selected):
- Same Width / Same Height across all selected widgets

**Snap toggle** — enable/disable snap-to-grid (8px); blue indicator when active. Hold **Shift** at any time while the canvas has focus to temporarily disable snap — the button dims immediately on key-down and restores on key-up (works during move, resize, form resize, and widget draw)

**Grid Layout popup** — ⊡ button opens a `Toplevel` with Make Grid and H/V nudge controls for arranging widgets in a regular grid automatically; H/V nudge buttons step by 8px, or **1px when Shift is held**

**Tab order toggle** — `⇥` button shows or hides numbered blue badges on every widget indicating its tab/z-order position; toggles as a sticky button (lit blue when active)

**Right cluster — History & Clipboard:**

| Action | Shortcut |
|---|---|
| Undo | Ctrl+Z |
| Redo | Ctrl+Y |
| Copy | Ctrl+C |
| Paste | Ctrl+V |

Undo/Redo is snapshot-based (max 50 states). Every mutation — move, resize, add, delete, prop change — is snapshotted before it happens. Also accessible via right-click context menu on the canvas.

**Toolbar button states** — buttons dim to #555555 and ignore clicks when their action doesn't apply (alignment/distribute/size require ≥2/3 widgets selected; undo/redo track stack depth; copy requires a selection; paste requires clipboard content).

## Properties Panel

Right-side panel with a **control selector dropdown** at the top and Property/Value columns below. Click any value to edit inline; geometry updates live as you drag on the canvas.

### Font Picker

The `font` property row opens a font chooser dialog pre-populated with the widget's current family, size, and style. Supports bold, italic, underline, and overstrike. The result is written back as a string tkinter accepts natively (e.g. `"Arial 12 bold"`).

### Color Picker
Background and Foreground properties open `tkinter.colorchooser`. The row tints immediately and the canvas widget updates live. New widgets get sensible default colors automatically. A `×` button appears on hover to clear the value back to default.

### State
Button, Entry, Text, Combobox, and other widgets expose a `state` dropdown (normal / readonly / disabled). Selecting readonly or disabled reveals conditional color rows (`readonlybackground`, `disabledbackground`, `disabledforeground`) that auto-fill with defaults and hide when not applicable.

### Validation
Entry and Spinbox expose a `validate` dropdown (key / focus / all / etc.) with `--vcmd`, `--args`, and `--ivcmd` sub-rows. The `--args` field has a preset dropdown for common tkinter substitution codes (`%P`, `%P, %S`, etc.). Codegen emits `self.register(self.method)` wiring automatically.

Hovering a substitution code in the `--args` dropdown shows its meaning in the hint bar at the bottom of the Properties panel (e.g. `%P` → *proposed value after the edit*, `%S` → *string being inserted or deleted*, `%d` → *action type: 0=delete 1=insert*).

### Variable Binding
Supported widgets expose a Variable section: set a name, type (StringVar / IntVar / DoubleVar / BooleanVar), and initial value. Codegen emits the declaration and wires `textvariable=` / `variable=` automatically.

**Variable picker popup** — click the variable name field to open a popup listing every variable defined on the form (from widget bindings and menu check/radio items) with its type; live-filters as you type, or type a new name manually.

### Widget Anchoring

The `anchor` row in Properties shows a 3×3 picker grid. Selecting an anchor position (e.g. bottom-right) causes the widget to reposition and resize relative to the form at runtime — so it stays pinned to that corner as the window is resized.

- **Live preview** — while you drag a form resize handle on the canvas, anchored widgets reposition in real time, matching the runtime behavior
- **Shift+resize suppresses anchors** — hold Shift while dragging a form handle to keep all widgets frozen (useful for checking the layout without anchor interference)
- **Hover hint** — the anchor row's status-bar hint describes the selected anchor and reminds you of the Shift shortcut
- A `×` button appears on hover to clear the anchor back to none

Codegen emits a `_apply_anchor_layout()` method that is called in `__init__` after `_build_ui()`.

### Multi-Select Properties

When multiple widgets are selected, the Properties panel shows the **intersection** of all their shared property names. Values that differ across the selection are shown blank; typing a new value applies it to all selected widgets at once. Color pickers, enum dropdowns, and text fields all work in multi-select. The font picker and list editor are single-select only.

### Form Properties
Click the canvas background to inspect the form: title, size, background color, border style (Sizable / Fixed / None), maximize box, and **always on top** (pins the window above all other windows). Border style and maximize box stay in sync automatically.

### Menu Bar
A `menu bar` row in form properties opens the **Menu Editor** — see [Menu Editor](#menu-editor) below.

### Hover Interactions
- Mousing over any row highlights it in blue
- Color props and optional props show a `×` button on hover to clear back to default
- A short description of each property appears in the status bar as you hover

## Events Tab

Every widget exposes its full event list (click, dblclick, keypress, focusin, change, and more).

- **Click the value column** (right of the name/value split) to open the handler picker or type a custom name; clicking the name column alone does nothing
- **Double-click a wired row** to jump directly to that handler in the editor (auto-generates code first if dirty)
- Handler names that don't start with `_` are flagged red — non-underscore names go to the Functions section instead of the Events stub section
- Wired rows show a `×` button on hover to clear the handler
- **✦ auto-wire button** appears on hover for unwired rows
- **? Events** row at the bottom opens a paginated guide explaining events, wiring steps, naming conventions, and a full reference table for the selected widget type

**`command` event** — for Button, Checkbutton, Radiobutton, Scale, Spinbox this generates `command=self.method` as a constructor kwarg (not `.bind()`).

**`comboselected` event** — for Combobox, generates `.bind("<<ComboboxSelected>>", ...)`.

**Form events** — clicking the canvas background and switching to the Events tab exposes form-level events: load, activate, deactivate, unload, resize. Wiring them generates `.bind()` calls and stubs the handler methods.

**Handler picker** — every event handler cell has a ▾ button that opens a scrollable popup listing all handlers already defined on the form. Hover a row to preview the name in the entry field. Useful for reusing an existing handler across multiple events. The Menu Editor Command field has the same picker.

## Handlers Tab

The **Handlers** tab (visible when a widget or the form is selected) shows every method that IDOL can generate for the selected widget — not just event callbacks but also utility methods (e.g. `_set_always_on_top`, validate helpers).

**Checkbox column (x ≤ 28px):**
- **Click** the checkbox area to toggle a handler on or off; unchecked handlers are not emitted during codegen
- **Double-clicking** the checkbox area also toggles, matching single-click behavior

**Name column (right of checkbox):**
- **Single-click** does nothing — prevents accidental navigation
- **Double-click an unchecked row** — checks the handler and enables it
- **Double-click a checked row** — auto-generates code if dirty and navigates to that handler in the editor (same behavior as double-clicking a wired event row in Events tab)

A short **hint bar** at the bottom of the Handlers tab shows a description of the hovered handler.

## Order Tab

The **Order** tab in the Properties panel shows all widgets on the form as a canvas-rendered numbered list in their current tab/z-order.

- Drag any row up or down to reorder it — the canvas updates immediately, badges refresh, and undo is supported
- The order here is both the **Tab key focus sequence** and the **z-order** (earlier entries are beneath later ones)
- The **`⇥` toolbar button** toggles numbered blue badges directly on the canvas widgets so you can see the order at a glance without switching to the Order tab
- A permanent hint in the status bar reminds you of what the Order tab does when it is active

## Widget Containment

Frame and LabelFrame act as parent containers:

- Dropping a widget onto a Frame/LabelFrame auto-parents it (coordinates stored relative to the container's content area, matching how tkinter's `place()` works)
- Drag a widget out of a container to reparent it to the form or another container
- The `parent` row in Properties is read-only — drag on the canvas to reparent
- LabelFrame applies a 17px label-area offset automatically
- Codegen uses the container as the parent argument for `place()`

## Menu Editor

A VB6-style dialog accessible from the `menu bar` form property row.

**Fields:** Caption, Name, Shortcut, Enabled, Visible, **Type** (Command / Checkbutton / Radiobutton), **Variable** (with variable picker popup), **Command** (with handler picker popup), **Value**

**Controls:** ← → ↑ ↓ arrow buttons to indent (create submenus) and reorder; Insert / **Separator** / Delete / Next; indented preview listbox; hover hint bar at the bottom describing each field; OK / Cancel

**& access-key in captions** — prefix a letter with `&` (e.g. `&File`) to set an access-key underline. The `&` is stripped from the rendered caption and codegen emits the matching `underline=N` kwarg.

**Behavior:**
- Adding a menu bar shifts all top-level widgets down 20px and increases form height; removing reverses this
- Live menu bar strip rendered on canvas below the title bar
- Codegen emits the full `tk.Menu` hierarchy — `add_checkbutton`/`add_radiobutton` for check/radio items with `variable=`, `value=`, and `command=` kwargs; auto-stubs all leaf command handlers; emits `BooleanVar`/`StringVar` declarations for menu variables; emits `self.bind("<shortcut>", handler)` for items with both a shortcut and a handler

## Double-Click Navigation

Double-clicking a widget with events:
1. Auto-generates code if the form has ungenerated changes
2. Switches to Editor mode and places the cursor on the first event handler

Double-clicking a widget with no events switches to the Events tab.

**Double-clicking a wired event row** in the Events tab jumps directly to that specific handler in the editor.

**Double-clicking a checked handler row** in the Handlers tab also navigates to that handler (double-clicking an unchecked row enables it instead).

**Double-clicking a wired event row in the Properties panel** (the property name column) also jumps to that handler — so you can navigate to code from any event.

Clicking a menu item on the canvas dropdown navigates to its handler the same way.

## Multi-Form Projects

A project can contain any number of forms. Each form has its own canvas, `.form.json` sidecar, and generated `.py` file.

### Form Types

| Type | Base class | Use for |
|---|---|---|
| **Main Window** | `tk.Tk` | The app's primary window |
| **Dialog Window** | `tk.Toplevel` | Secondary windows opened from a main form |

### FORMS Tree

The **FORMS** panel at the top of the left pane shows the full form hierarchy:

- **Main forms** appear at top level with a `⬜` icon
- **Linked dialogs** appear indented below their parent form with a `⧉` icon
- **Unlinked dialogs** appear in a dim "Unlinked" section at the bottom

Click any row to switch the canvas to that form (the current form is auto-saved first).

### Creating a New Form

Click the `+` button in the FORMS header or use `Designer → New Form…`. The dialog has:

- **Form Name** — must be a valid Python identifier
- **Type** — Main Window or Dialog Window
- **Link to** — (Dialog only) choose a parent main form or "None (unlinked)"; defaults to the first existing main form

The new form appears in the tree immediately and the canvas switches to it.

### Linking and Unlinking Dialogs

**Drag to link** — drag a dialog row and drop it onto any main form row. The target form highlights blue while hovering. A ghost label (`⧉ name`) follows the cursor. Releasing over a form links the dialog to it; releasing elsewhere cancels.

**Unlink** — hover a linked dialog row to reveal a `×` button on the right side. Clicking it removes the link.

A dialog can be linked to multiple main forms simultaneously.

### Dialog Code Generation

Dialogs generate a `tk.Toplevel` subclass. Closing the window calls `_on_close` (a preserved stub) which hides it rather than destroying it, keeping the instance alive for reuse:

```python
class MyDialog(tk.Toplevel):
    def __init__(self, parent, **kwargs):
        # ── IDOL:BEGIN ──
        super().__init__(parent, **kwargs)
        self.withdraw()
        self.title("My Dialog")
        self.geometry("400x300")
        # ── IDOL:END ──

        # ── IDOL:BEGIN ──
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # ── IDOL:END ──

    # ── Events ──────────────────────────────────────────────────
    def _on_close(self):
        self.withdraw()
```

The parent main form stores the dialog instance on creation and exposes an opener:

```python
# ── IDOL:DIALOG_IMPORTS:BEGIN ──
from MyDialog import MyDialog
# ── IDOL:DIALOG_IMPORTS:END ──

class Form1(tk.Tk):
    def __init__(self):
        # ── IDOL:BEGIN ──
        super().__init__()
        self.dlg_MyDialog = MyDialog(self)   # created once, reused
        # ── IDOL:END ──

    # ── Events ──────────────────────────────────────────────────
    def _open_MyDialog(self):
        self.dlg_MyDialog.deiconify()
```

Key points:
- `self.dlg_MyDialog` gives the parent direct access to the dialog's widgets and state at any time
- `_on_close` and `_open_MyDialog` are both preserved event stubs — customize them freely, bodies survive regeneration
- The `IDOL:DIALOG_IMPORTS` block is fully auto-managed — regenerated from the current link state on every codegen run; do not add your own imports inside it
- **Codegen order** — dialogs are written before main forms so their imports resolve correctly

## Code Generation

`Designer → Generate Code` (`Ctrl+Shift+G`) writes clean, class-based Python:

```python
import tkinter as tk
# ── IDOL:IMPORTS:BEGIN ── (add your imports between the markers)
# Add your imports here
# ── IDOL:IMPORTS:END ──

class Form1(tk.Tk):
    def __init__(self):
        # ── IDOL:BEGIN ────── (generated — do not edit inside markers)
        super().__init__()
        self.title("My App")
        self.geometry("800x600")
        self.result_var = tk.StringVar()
        # ── IDOL:END ──────

        # Your __init__ code here is preserved across regeneration

        # ── IDOL:BEGIN ──────
        self._build_ui()
        # ── IDOL:END ──────

    def _build_ui(self):
        self.btn1 = tk.Button(self, text="Click Me", command=self._btn1_click)
        self.btn1.place(x=10, y=10, width=100, height=30)

    # ── Events ───────────────────────────────────────────────────────────────

    def _btn1_click(self, *args):
        pass  # TODO

    # ── Functions ────────────────────────────────────────────────────────────
    # Methods defined here are preserved across code generation.
```

## User Code Preservation

Regenerating never discards code you wrote:

- Event handler **bodies** are extracted and spliced back in verbatim, including any **leading comment lines** before the first statement
- Event handler **signatures** are preserved — change `*args` to `event: tk.Event` once and IDOL keeps it on every subsequent regeneration
- User **imports** between the `IDOL:IMPORTS:BEGIN/END` markers survive regeneration
- The `IDOL:DIALOG_IMPORTS` block is fully auto-managed (always regenerated from link state) — do not add manual imports inside it; use `IDOL:IMPORTS` for your own imports
- Helper methods in the `# ── Functions ──` section survive verbatim
- Code in the two `__init__` user zones (between the IDOL marker blocks) is preserved

## Codegen Confirmation Prompt

When Generate Code would overwrite a file, a single dark-themed dialog asks for confirmation. A **"don't ask again this session"** checkbox suppresses subsequent prompts for the rest of the session. The checkbox resets on next launch.

## Manual Edits Detection

If you edit the generated `.py` by hand, IDOL detects the change via SHA-256 checksum the next time you click Generate Code and warns you. Event handlers, helpers, and `__init__` code are always preserved regardless.

## Persistent Form Model

The canvas state is stored in a `.form.json` sidecar file next to the generated `.py`. The JSON is the source of truth; the `.py` is a build artifact. Both files are version-control friendly.

**Saving the form JSON:**
- `Designer → Save Form` writes all open form JSONs to disk immediately; the menu item is enabled whenever there are unsaved designer changes
- **Exit prompt** — if any form has unsaved changes when you quit IDOL, a dialog asks **Save / Don't Save / Cancel**; choosing Save writes all dirty forms before exiting, Don't Save discards them, and Cancel aborts the exit
- `Designer → Generate Code` also saves the form JSON as a side effect, so generating code always leaves the JSON in sync

## Project Type Gating

The Designer only appears for **Tkinter GUI App** projects. Command Line projects see only the standard editor with no extra UI.
