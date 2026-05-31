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
- **Arrow-key nudge** — 8px nudge (matching the snap grid) with arrow keys; hold **Shift** for 1px precision
- **Z-order** — Bring to Front / Send to Back preserved on every mutation
- **Menu bar strip** — live menu bar rendered below the title bar from your menu items; clicking a top-level name opens a native dropdown; clicking a command or check/radio item with a handler navigates to that handler in the editor
- **Canvas scrollbars** — the canvas has horizontal and vertical scrollbars with mousewheel support on all platforms (Windows/macOS via `<MouseWheel>`; Linux via `<Button-4>`/`<Button-5>`; hold **Shift** to scroll horizontally); the form recenters automatically after a resize drag

## Widget Palette

16 widget types in a scrollable toolbox with canvas-drawn mini-previews:

Button, Label, Entry, Text, Checkbutton, Radiobutton, Combobox, Listbox, Frame, LabelFrame, **Notebook**, Scale, Spinbox, Progressbar, Separator, **Canvas**

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
Background and Foreground properties open `tkinter.colorchooser`. The row tints immediately and the canvas widget updates live. Non-input widgets (Button, Label, Frame, etc.) start with no explicit background color, inheriting the OS default. Input widgets (Entry, Text, Listbox) default to white. A `×` button appears on hover to clear a color back to the OS default.

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

### Image Properties

Label, Button, and Canvas widgets support an `image` property. Click the row to open a file picker — the selected file is automatically copied into `<project>/images/` so the generated app is self-contained. A live thumbnail scaled to the widget bounds appears on the canvas immediately.

- **Compound** (Label and Button only) — positions the image relative to any text: `left`, `right`, `top`, `bottom`, `center`, `none`; when an image is set the canvas hides the text label to match runtime behaviour
- **PIL warning row** — if Pillow is not installed in the active project interpreter, an amber **⚠ click to install Pillow** row appears below the `image` row; clicking it streams `pip install pillow` into the Output panel and removes the warning on success
- **Anchor-aware resize** — when the widget has a size-changing anchor (`all`, `top`, `bottom`, `left`, `right`), codegen emits a `<Configure>` binding that reloads the `PhotoImage` at the new widget dimensions so the image scales live with the window

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

The **Handlers** tab shows every method IDOL can generate and lets you wire connectable handlers to widget events. It uses an **Available / Connected** split — no checkboxes.

### Available Section

Handlers that are not yet wired or enabled. A **⚡** button appears on hover:

- **Connectable handler** (e.g. `open_dialog`, `always_on_top`) — clicking ⚡ opens the **Connector** dialog where you pick a widget and an event; the wire is stored and the handler moves to Connected
- **Non-connectable handler** (e.g. `on_escape`, `on_return`) — clicking ⚡ enables it immediately; the handler appears in Connected wired to its built-in target

**`multi_wire` handlers** (currently `open_dialog`) stay in Available even after wiring so you can wire them to additional widget events — one wire per dialog.

**Available Components sub-section** — collapsed by default (▶ header); click the header to expand. Shows **all** connectable component handlers (e.g. `timer1_start`, `cd1_show_open`) regardless of whether they are already wired — handlers are reusable and can be connected to multiple widgets or menu items. Clicking ⚡ opens the Connector pre-selecting the current widget.

### Connected Section

Enabled or wired handlers, each showing their target on the right (e.g. `btn1.click` or `WM_DELETE_WINDOW`). Two floating buttons appear on hover:

- **×** — disconnects the wire or disables the handler
- **…** — opens the **Options Editor** for handlers that have named mode variants (e.g. `on_close` with hide vs destroy, `open_dialog` close-mode picker)

**⚡ Connected Components sub-section** (widget-selected only) — component handler methods already wired to this widget's events or menu items; **×** to disconnect, **…** to edit the wire or per-handler properties (dialog title, messagebox type and message, etc.).

### Options Editor

When a connected handler has named mode variants, the **…** button opens a picker with two-line rows — bold option name on line 1, orange description on line 2. Selecting an option updates the stub body or wire body and (for `open_dialog`) syncs the linked dialog's `_on_close` mode.

### open_dialog Handler

`open_dialog` (main forms only) wires a widget event to open a linked dialog. The Connector shows two dropdowns:

- **Dialog** — which linked dialog to open
- **Mode** — **hide (withdraw)** reuses the instance on next open; **destroy (exit)** recreates it fresh

Wiring automatically updates the linked dialog's `_on_close` option to match the chosen mode. Use the **…** button on a connected row to change the mode later — the dialog's `_on_close` updates automatically.

### When the Form is Selected

Both Available and Connected sections show all form-level handlers together with all component handlers from the tray, giving a full picture of what the form generates.

## Order Tab

The **Order** tab in the Properties panel shows all widgets on the form as a canvas-rendered numbered list in their current tab/z-order.

- Drag any row up or down to reorder it — the canvas updates immediately, badges refresh, and undo is supported
- The order here is both the **Tab key focus sequence** and the **z-order** (earlier entries are beneath later ones)
- The **`⇥` toolbar button** toggles numbered blue badges directly on the canvas widgets so you can see the order at a glance without switching to the Order tab
- A permanent hint in the status bar reminds you of what the Order tab does when it is active

**Notebook tab grouping** — when the form contains a Notebook, its children appear indented under teal tab-header rows (one per tab, in the Notebook's `tabs` property order). Dragging a child row across a tab header reassigns it to that tab — the canvas and codegen update automatically. Tab order badges are numbered independently within each tab.

## Widget Containment

Frame, LabelFrame, and Notebook act as parent containers:

- **Dropping or drawing** a widget onto a container auto-parents it (coordinates stored relative to the container's content area, matching how tkinter's `place()` works); children are clamped to the container bounds on drop
- Drag a widget out of a container to reparent it to the form or another container
- The `parent` row in Properties is read-only — drag on the canvas to reparent
- LabelFrame applies a 17px label-area offset automatically
- Codegen uses the container as the parent argument for `place()`
- **Deleting** a container removes all of its descendant widgets

## Notebook Widget

`ttk.Notebook` is a first-class container in the designer — drop it onto the canvas, then add widgets to each of its tabs.

- The canvas renders the tab strip with the active tab raised and inactive tabs dimmed, matching the native ttk.Notebook appearance
- **Switching tabs** on the canvas (click a tab label) selects the Notebook widget, clears resize handles, and shows/hides children so only the active tab's content is visible
- **Adding children** — with a palette tool armed, hover over the Notebook's content area; the cursor changes to a crosshair; dropping or drawing places the widget inside the active tab
- Each child has a `tab` property (the tab name string) that determines which tab it belongs to; reassign via the Order tab or by dragging across tab headers
- The **`<<NotebookTabChanged>>`** event is available in the Events tab; wiring it generates a `.bind()` call and a handler stub
- Codegen emits the full Notebook hierarchy: `ttk.Notebook`, one `ttk.Frame` per tab added with `.add(frame, text="Tab Name")`, and child widgets placed inside their tab's frame

## Menu Editor

A VB6-style dialog accessible from the `menu bar` form property row.

**Fields:** Caption, Name, Shortcut, Enabled, Visible, **Type** (Command / Checkbutton / Radiobutton), **Variable** (with variable picker popup), **Command** (with handler picker popup), **Value**

**Controls:** ← → ↑ ↓ arrow buttons to indent (create submenus) and reorder; Insert / **Separator** / Delete / Next; indented preview listbox; hover hint bar at the bottom describing each field; OK / Cancel

**& access-key in captions** — prefix a letter with `&` (e.g. `&File`) to set an access-key underline. The `&` is stripped from the rendered caption and codegen emits the matching `underline=N` kwarg.

**Behavior:**
- Adding a menu bar shifts all top-level widgets down 20px and increases form height; removing reverses this
- Live menu bar strip rendered on canvas below the title bar
- Codegen emits the full `tk.Menu` hierarchy — `add_checkbutton`/`add_radiobutton` for check/radio items with `variable=`, `value=`, and `command=` kwargs; auto-stubs all leaf command handlers; emits `BooleanVar`/`StringVar` declarations for menu variables; emits `self.bind("<shortcut>", handler)` for items with both a shortcut and a handler

## Non-Visual Components

Non-visual components (timers, dialogs, file pickers) live in the **component tray** — a chip strip below the canvas. Click the **COMPONENTS** palette section to add one; the tray shows icon + name chips; selecting a chip reveals its properties and handlers in the Properties / Handlers panels. Codegen emits init code and all handler stubs into the generated `.py`; user bodies survive regeneration automatically.

**Wiring connectable handlers** — handlers marked ⚡ can be wired to widget events or menu items via the [Connector](#handlers-tab). The Connector lists both widget events and any non-cascade command menu items so a single handler can be invoked from a button click, a keyboard shortcut, or a menu command — no extra wrapper code needed.

**Menu item wiring** — wiring a component handler to a menu item stores the method reference directly on the menu item (`command_handler`); codegen emits `command=self._cd1_show_open` instead of the default `_{name}_click` wrapper.

**Selective imports** — codegen only emits dialog imports your form actually uses (e.g. `from tkinter import filedialog` appears only if `_show_open` or `_show_save` is wired; `messagebox` only if `_show_message` is wired).

### Timer

`self.after()` periodic callback — no threading, no locks.

| Property | Description |
|---|---|
| Interval | Milliseconds between ticks |
| Enabled | Start timer on form load |

| Handler | Description |
|---|---|
| `_tick` | User logic; called every interval |
| `_start` ⚡ | Start the timer; wire to a button or menu item |
| `_stop` ⚡ | Stop the timer |

### Socket

TCP socket component — **Server** listens for incoming connections; **Client** connects to a remote host. All network I/O runs on daemon threads; callbacks dispatch back to the main thread via `self.after(0, ...)` so tkinter widgets are always updated safely.

**Setup dialog** — dropping a Socket from the palette immediately shows a setup dialog:
- **Type** — Server or Client
- **Host / Port** — remote host (client) or bind address (server) and TCP port
- **Scaffold starter widgets** (optional) — three pre-wired kits:
  - **Connect / Disconnect** — a `btn_connect` toggle button (Listen→Stop or Connect→Disconnect) and a `lbl_status` label that updates colour and text automatically through `on_connect` / `on_disconnect`
  - **Chat** — a read-only `txt_chat` (Text + scrollbar), a `ent_message` Entry, and a `btn_send` button; sending a message appends `[You] text` to the log; received text appears directly in the log
  - **File Transfer** — a `pb_transfer` Progressbar (updates chunk-by-chunk on both send and receive), a `lbl_file` status label, and a `btn_send_file` button that opens a file picker and sends immediately on a daemon thread

When the **File Transfer** scaffold is active all communication uses a **length-prefix framing protocol** — `struct.pack('>Q', payload_size)` prepended to every message so the receiver knows the exact payload length before reading. Text and binary data share the same wire format; the receiver distinguishes them by attempting UTF-8 decode.

| Property | Applies to | Description |
|---|---|---|
| socket type | Both | "server" or "client" — set by dialog, read-only |
| host | Both | Remote host (client) / bind address (server) |
| port | Both | TCP port (default 8080) |
| encoding | Both | Text encoding for send/receive text (default utf-8) |
| timeout | Both | Connect timeout in seconds (default 5.0) |
| buffer size | Both | recv() chunk size in bytes (default 4096) |
| auto connect | Both | Start listening / connect automatically on form load |
| max clients | Server | Maximum simultaneous client connections (default 5) |
| bind address | Server | Network interface to bind (default 0.0.0.0) |
| retry on fail | Client | Retry automatically after a failed connect |
| retry interval | Client | Seconds between retries (default 3.0) |

| Handler | Description |
|---|---|
| `_toggle_connect` ⚡ | One-button toggle — used by the Connect/Disconnect scaffold |
| `_start` ⚡ | [Server] Begin listening — for separate Listen/Stop buttons |
| `_connect` ⚡ | [Client] Connect to server — for separate Connect/Disconnect buttons |
| `_disconnect` ⚡ | Close all connections |
| `_send_text(text)` | Send a UTF-8 string to connected peer(s) |
| `_send_file(data)` | Send raw bytes (framed when File Transfer scaffold active) |
| `_quick_send` | [Chat scaffold] Read Entry and send; echoes in chat log |
| `_pick_and_send_file` | [File Transfer scaffold] Open file picker and send |
| `_on_connect` | Fired when a connection is established |
| `_on_disconnect` | Fired when a connection is closed |
| `_on_receive_text(text)` | Fired with decoded string data |
| `_on_receive_file(data)` | Fired with raw bytes (saved to disk by scaffold) |
| `_on_send_text(text)` | Fired after a text send completes |
| `_on_send_file(data)` | Fired after a file send completes |
| `_on_error(error)` | Any socket exception |
| `_on_timeout` | Connect or recv timeout |

### CommonDialog

A multi-mode wrapper around tkinter's built-in dialog functions. Each handler is independently wired and has its own title / message configuration.

| Handler | Dialog invoked | Result |
|---|---|---|
| `_show_open` ⚡ | `filedialog.askopenfilename` | Path stored in `_cd1_result`; `_on_file_selected` stub called |
| `_show_save` ⚡ | `filedialog.asksaveasfilename` | Path stored in `_cd1_result`; `_on_file_selected` stub called |
| `_show_color` ⚡ | `colorchooser.askcolor` | Color tuple stored in `_cd1_result`; `_on_color_selected` stub called |
| `_show_input` ⚡ | `simpledialog.askstring` | String stored in `_cd1_result`; `_on_input_received` stub called |
| `_show_message` ⚡ | `messagebox` (ok/yesno/warning/etc.) | Button string stored in `_cd1_result`; `_on_message_result` stub called |

**Per-handler configuration** — click **…** on a connected handler row to set that handler's dialog title. For `_show_message`, you also set the message body and messagebox type (ok, okcancel, yesno, warning, error, etc.). All configuration is stored in the component props and written into the generated code.

**`parent=self`** — all dialog calls pass the form as parent so focus returns to the correct window after the dialog closes.

## Double-Click Navigation

Double-clicking a widget with events:
1. Auto-generates code if the form has ungenerated changes
2. Switches to Editor mode and places the cursor on the first event handler

Double-clicking a widget with no events switches to the Events tab.

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

Click any row to switch the canvas to that form (the current form is auto-saved first). The companion `.py` opens automatically as an editor tab so you can flip between visual and code views without hunting for the file.

**Missing forms** — if a session is restored and a form's `.form.json` can no longer be found on disk, its row is shown in red with a tooltip explaining the missing path. The form can be removed with the right-click menu.

### Set as Main

Designate which form is the app entry point:

- **Right-click** a main form row → **Set as Main**
- **Double-click** a main form row to set it as main directly

When a form is set as main, IDOL:
1. Writes (or overwrites) `main.py` with the standard `from FormName import FormName; FormName().mainloop()` pattern, marked with a `# Generated by IDOL Designer` header
2. Pins that file as the ▶ run entry in the status bar so **Run** always launches the correct form
3. Shows **▶ FormName** in teal in the FORMS panel header

The ▶ indicator in the FORMS panel follows the **active run entry** — if you manually change the run entry selector in the status bar, the indicator updates automatically. In **Active Tab** mode the indicator highlights whichever form corresponds to the currently active editor tab.

### FORMS Tree X Button

- **X on a main form row** — removes that form (and its linked dialogs) from the designer. Shows a confirmation prompt before removing. The underlying `.form.json` and `.py` files are not deleted.
- **X on a linked dialog row** — unlinks the dialog from its parent (removes the link only; does not remove the form from the designer or delete files)

### Session Persistence

The designer state is saved as part of the project session:
- Which forms were open in the designer are restored on next launch
- When a project reopens, linked dialogs load automatically alongside their parent form
- If the designer was active when IDOL last closed, it re-enters designer mode on startup

**Auto-loading linked dialogs** — when you open a form that was created in another directory (via `Designer → Open Form…` or the Explorer right-click menu), IDOL automatically locates and copies both the form's `.form.json` and the `.py` for any linked dialogs it finds in the same source directory, then loads them alongside the parent form.

### Creating a New Form

Click the `+` button in the FORMS header or use `Designer → New Form…`. The dialog has:

- **Form Name** — must be a valid Python identifier; auto-fills as `Form{n}` or `Dialog{n}` (next available number) and toggles between the two prefixes when you flip the Type radio, as long as you haven't typed a custom name
- **Type** — Main Window or Dialog Window; defaults to **Main Window** when the project has no forms yet, otherwise Dialog
- **Link to** — (Dialog only) choose a parent main form or "None (unlinked)"; defaults to the first existing main form

On create, IDOL writes the `.form.json`, generates the `.py` immediately, opens it as an editor tab, refreshes the Explorer, and switches the canvas to the new form.

### Linking and Unlinking Dialogs

**Drag to link** — drag a dialog row and drop it onto any main form row. The target form highlights blue while hovering. A ghost label (`⧉ name`) follows the cursor. Releasing over a form links the dialog to it; releasing elsewhere cancels.

**Unlink** — hover a linked dialog row to reveal a `×` button on the right side. Clicking it removes the link.

A dialog can be linked to multiple main forms simultaneously.

### Dialog Code Generation

Dialogs generate a `tk.Toplevel` subclass. Closing the window calls `_on_close` (a preserved stub) which hides it rather than destroying it, keeping the instance alive for reuse:

```python
class MyDialog(tk.Toplevel):
    def __init__(self, parent, **kwargs):
        # ── IDOL:BEGIN ─────────────────────(Do not modify below)─────────────────────
        super().__init__(parent, **kwargs)
        self.withdraw()
        self.title("My Dialog")
        self.geometry("400x300")
        # ── IDOL:END ───────────────────────(Do not modify above)─────────────────────

        # ── IDOL:BEGIN ─────────────────────(Do not modify below)─────────────────────
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus()
        # ── IDOL:END ───────────────────────(Do not modify above)─────────────────────

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
        # ── IDOL:BEGIN ─────────────────────(Do not modify below)─────────────────────
        super().__init__()
        self.dlg_MyDialog = MyDialog(self)   # created once, reused
        self.focus()
        # ── IDOL:END ───────────────────────(Do not modify above)─────────────────────

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

**Auto-generation** — code is regenerated automatically 1.5 seconds after any canvas or property change. Rapid edits coalesce into a single run. You can also trigger it manually with `Designer → Generate Code` (`Ctrl+Shift+G`).

```python
import tkinter as tk
# ── IDOL:IMPORTS:BEGIN ─────────────────────────────────────────────────────────
# Add your imports here
# ── IDOL:IMPORTS:END ───────────────────────────────────────────────────────────

class Form1(tk.Tk):
    def __init__(self):
        # ── IDOL:BEGIN ─────────────────────(Do not modify below)─────────────────────
        super().__init__()
        self.title("My App")
        self.geometry("800x600")
        self.result_var = tk.StringVar()
        # ── IDOL:END ───────────────────────(Do not modify above)─────────────────────

        # Your __init__ code here is preserved across regeneration

        # ── IDOL:BEGIN ─────────────────────(Do not modify below)─────────────────────
        self._build_ui()
        # ── IDOL:END ───────────────────────(Do not modify above)─────────────────────

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

- Event handler **bodies** are extracted and spliced back in verbatim, including **leading and trailing comment lines** (comments before the first statement and comments at the end of the body)
- Event handler **signatures** are preserved — change `*args` to `event: tk.Event` once and IDOL keeps it on every subsequent regeneration
- User **imports** between the `IDOL:IMPORTS:BEGIN/END` markers survive regeneration
- The `IDOL:DIALOG_IMPORTS` block is fully auto-managed (always regenerated from link state) — do not add manual imports inside it; use `IDOL:IMPORTS` for your own imports
- Helper methods in the `# ── Functions ──` section survive verbatim
- Code in the two `__init__` user zones (between the IDOL marker blocks) is preserved

## Codegen — No Confirmation Needed

Code generation runs silently — no confirmation dialog. Manual edits to the `.py` are always preserved (event bodies, signatures, helper methods, `__init__` zones), so regeneration is safe to run at any time without prompting.

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

`Pro tip: To open Designer without a project go to Designer -> New Form...`
