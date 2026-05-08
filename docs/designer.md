# GUI Designer

IDOL includes a full **VB6-style drag-and-drop GUI builder** for Tkinter applications — the only Python IDE with a visual form designer built in.

> **Activation:** The Designer only appears for **Tkinter GUI App** projects. Create one with `File → New Project…` and select **Tkinter GUI App** — the wizard scaffolds `Form1.py`, `Form1.form.json`, and a `main.py` entry point, then drops you straight into the canvas.

## Layout

```
┌─────────────┬──────────────────────────┬──────────────────┐
│ Palette     │  [Editor]  [Designer]    │ Properties       │
│ (reuses     │  Toolbar (align/snap)    │ Panel            │
│  explorer   │  Canvas (dotted grid)    │                  │
│  slot)      │                          │ Name: btn1       │
│             │  ┌────────────────────┐  │ Text: Click Me   │
│ [Button]    │  │ Form1              │  │ Width: 90        │
│ [Label]     │  │  [Click Me]        │  │ ── Events ──     │
│ [Entry] ... │  └────────────────────┘  │ Click: [stub ▼]  │
└─────────────┴──────────────────────────┴──────────────────┘
```

Entering Designer mode swaps the File Explorer out and the Widget Palette in — same left-panel slot, no floating windows. Exiting Designer restores the Explorer.

## Canvas

- **Dotted-grid design surface** — form rendered at real size with a simulated title bar and drop shadow
- **Widgets render realistically** — raised buttons, sunken entries, filled progress bars, checked checkboxes, and more
- **Click to select** — blue dashed border + 8 white resize handles appear on the selected widget
- **Drag to move** — repositions with 8px snap-to-grid
- **Drag a handle to resize** — snapped to the same 8px grid
- **Multi-select** — rubber-band drag to select multiple widgets; Ctrl+Click to toggle individual widgets; drag the group to move all at once
- **Copy / Paste** — Ctrl+C / Ctrl+V to duplicate; right-click context menu with Copy, Paste, Delete, Bring to Front, Send to Back
- **Arrow-key nudge** — 1px precision positioning with arrow keys
- **Z-order** — Bring to Front / Send to Back preserved on every mutation
- **Menu bar strip** — live menu bar rendered below the title bar from your menu items; clicking a top-level name opens a native dropdown; clicking a command or check/radio item with a handler navigates to that handler in the editor

## Widget Palette

14 widget types in a scrollable toolbox with canvas-drawn mini-previews:

Button, Label, Entry, Text, Checkbutton, Radiobutton, Combobox, Listbox, Frame, LabelFrame, Scale, Spinbox, Progressbar, Separator

## Toolbar

A horizontal strip above the canvas with alignment and snap controls:

- **Align** — Align Left, Right, Top, Bottom, Center Horizontally, Center Vertically (requires ≥2 selected)
- **Distribute** — Equal horizontal / vertical spacing (requires ≥3 selected)
- **Size** — Same Width / Same Height across selected widgets
- **Snap toggle** — enable/disable snap-to-grid; blue indicator when active

## Properties Panel

Right-side panel with a **control selector dropdown** at the top and Property/Value columns below. Click any value to edit inline; geometry updates live as you drag on the canvas.

### Color Picker
Background and Foreground properties open `tkinter.colorchooser`. The row tints immediately and the canvas widget updates live. New widgets get sensible default colors automatically. A `×` button appears on hover to clear the value back to default.

### State
Button, Entry, Text, Combobox, and other widgets expose a `state` dropdown (normal / readonly / disabled). Selecting readonly or disabled reveals conditional color rows (`readonlybackground`, `disabledbackground`, `disabledforeground`) that auto-fill with defaults and hide when not applicable.

### Validation
Entry and Spinbox expose a `validate` dropdown (key / focus / all / etc.) with `--vcmd`, `--args`, and `--ivcmd` sub-rows. The `--args` field has a preset dropdown for common tkinter substitution codes (`%P`, `%P, %S`, etc.). Codegen emits `self.register(self.method)` wiring automatically.

### Variable Binding
Supported widgets expose a Variable section: set a name, type (StringVar / IntVar / DoubleVar / BooleanVar), and initial value. Codegen emits the declaration and wires `textvariable=` / `variable=` automatically.

**Variable picker popup** — click the variable name field to open a popup listing every variable defined on the form (from widget bindings and menu check/radio items) with its type; live-filters as you type, or type a new name manually.

### Form Properties
Click the canvas background to inspect the form: title, size, background color, border style (Sizable / Fixed / None), and maximize box. Border style and maximize box stay in sync automatically.

### Menu Bar
A `menu bar` row in form properties opens the **Menu Editor** — see [Menu Editor](#menu-editor) below.

### Hover Interactions
- Mousing over any row highlights it in blue
- Color props and optional props show a `×` button on hover to clear back to default
- A short description of each property appears in the status bar as you hover

## Events Tab

Every widget exposes its full event list (click, dblclick, keypress, focusin, change, and more).

- Click an event name to auto-wire a default handler
- Type a custom method name to override
- Handler names that don't start with `_` are flagged red — non-underscore names go to the Functions section instead of the Events stub section
- Wired rows show a `×` button on hover to clear the handler
- **✦ auto-wire button** appears on hover for unwired rows
- **? Events** row at the bottom opens a paginated guide explaining events, wiring steps, naming conventions, and a full reference table for the selected widget type

**`command` event** — for Button, Checkbutton, Radiobutton, Scale, Spinbox this generates `command=self.method` as a constructor kwarg (not `.bind()`).

**`comboselected` event** — for Combobox, generates `.bind("<<ComboboxSelected>>", ...)`.

## Widget Containment

Frame and LabelFrame act as parent containers:

- Dropping a widget onto a Frame/LabelFrame auto-parents it (coordinates stored relative to the container's content area, matching how tkinter's `place()` works)
- Drag a widget out of a container to reparent it to the form or another container
- The `parent` row in Properties is read-only — drag on the canvas to reparent
- LabelFrame applies a 17px label-area offset automatically
- Codegen uses the container as the parent argument for `place()`

## Menu Editor

A VB6-style dialog accessible from the `menu bar` form property row.

**Fields:** Caption, Name, Shortcut, Enabled, Visible, **Type** (Command / Checkbutton / Radiobutton), **Variable** (with variable picker popup), **Command**, **Value**

**Controls:** ← → ↑ ↓ arrow buttons to indent (create submenus) and reorder; Insert / Delete / Next; indented preview listbox; hover hint bar at the bottom describing each field; OK / Cancel

**Behavior:**
- Adding a menu bar shifts all top-level widgets down 20px and increases form height; removing reverses this
- Live menu bar strip rendered on canvas below the title bar
- Codegen emits the full `tk.Menu` hierarchy — `add_checkbutton`/`add_radiobutton` for check/radio items with `variable=`, `value=`, and `command=` kwargs; auto-stubs all leaf command handlers; emits `BooleanVar`/`StringVar` declarations for menu variables; emits `self.bind("<shortcut>", handler)` for items with both a shortcut and a handler

## Double-Click Navigation

Double-clicking a widget with events:
1. Auto-generates code if the form has ungenerated changes
2. Switches to Editor mode and places the cursor on the first event handler

Double-clicking a widget with no events switches to the Events tab.

Clicking a menu item on the canvas dropdown navigates to its handler the same way.

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

- Event handler **bodies** are extracted and spliced back in verbatim
- Event handler **signatures** are preserved — change `*args` to `event: tk.Event` once and IDOL keeps it on every subsequent regeneration
- User **imports** between the `IDOL:IMPORTS:BEGIN/END` markers survive regeneration
- Helper methods in the `# ── Functions ──` section survive verbatim
- Code in the two `__init__` user zones (between the IDOL marker blocks) is preserved

## Manual Edits Detection

If you edit the generated `.py` by hand, IDOL detects the change via SHA-256 checksum the next time you click Generate Code and warns you. Event handlers, helpers, and `__init__` code are always preserved regardless.

## Persistent Form Model

The canvas state is stored in a `.form.json` sidecar file next to the generated `.py`. The JSON is the source of truth; the `.py` is a build artifact. Both files are version-control friendly.

## Project Type Gating

The Designer only appears for **Tkinter GUI App** projects. Command Line projects see only the standard editor with no extra UI.
