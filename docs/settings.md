# Settings

Open with **Ctrl+,** (Cmd+, on macOS), **View → Settings**, or the Settings entry
on the Welcome tab. It opens as a tab, so you can leave it up while trying a
change out.

Left column picks a category; the search box at the top spans every category at
once, so you can find a setting without knowing where it was filed. Search
matches the setting's name, its description, and its underlying key — useful
when you have the key from a config file rather than the label.

Every change applies immediately. There is no Save button and no OK/Cancel.

## Reset

A **↺** appears next to any setting that differs from its default. Click it to
put the default back. No arrow means the setting is untouched, so the panel also
answers "what have I changed?" at a glance.

## Where settings are stored

IDOL keeps state in three places, and which one a thing belongs to is decided by
a single question:

| | The question it answers | Stored in | Travels with |
|---|---|---|---|
| **Preference** | How do I like my IDE? | `~/.idol/settings.json` | you, across every project |
| **Workspace state** | What was I doing here? | `<project>.idol-project` | the project |
| **Project config** | How is this codebase built? | files in the repo (`ruff.toml`, `environment.yml`) | the code, into git |

The Settings panel edits **preferences**. Things like open tabs, pane sizes and
the run configuration are workspace state and follow the project instead. Lint
rules are project config — when Settings grows a page for those, it will edit
the project's `ruff.toml` rather than keep a second copy of the rules.

`settings.json` only records what you have actually changed. Anything at its
default is absent from the file, which is what lets a future IDOL improve a
default without overriding a choice you made.

## Categories

Sections appear only once they have something in them.

### Appearance

| Setting | What it does |
|---|---|
| Theme | Editor and sidebar colour scheme. Also on **View → Theme** — the same value, two ways to reach it. |
| Show sidebar | Explorer, outline, references and source control. Also **Ctrl+B**. |
| Show bottom panel | Output, terminal, problems and debug. |

### Editor

| Setting | What it does |
|---|---|
| Font | Family, size and style for every editor tab. **Ctrl+L** opens the same chooser directly. |
| Show minimap | The scaled overview down the right edge. |
| Tab size | Spaces inserted by Tab in a new tab. A file whose own indentation is detected keeps that instead. |
| Highlight active line | Tint the line the cursor is on. |
| Active line colour | Overrides the theme's own highlight. Reset to follow whichever theme is active. |
| Autocomplete | Suggest completions as you type. |
| Auto-close brackets and quotes | Typing an opener inserts its closer, and typing the closer steps over it. Turning this off also stops the step-over, so a typed `)` is always the `)` you get. |

### AI

| Setting | What it does |
|---|---|
| Ollama server URL | Where the AI chat panel looks for a local Ollama server. |

### General

| Setting | What it does |
|---|---|
| Show Welcome tab on startup | Opens the Welcome tab when there is no session to restore. The tab's own checkbox sets the same value. |

## What is deliberately not a setting

**Zen Mode** (F10) is a live toggle and is not remembered. It is a focus mode
rather than a preference — reopening IDOL with everything hidden and no obvious
way back would be worse than retyping F10.

**Which bottom panel tab was open** is remembered, but per project, because it
describes what you were doing rather than how you like things.

## Upgrading from an older IDOL

Preferences used to be scattered: theme, editor font and minimap lived in the
session file, the Ollama URL with them, and the Welcome-tab checkbox in
`recent.json`. Because the session was also written into each project, opening
a different project could silently change your theme and font.

They are moved into `settings.json` automatically the first time you launch.
Nothing is lost, and anything you had already customised wins over the imported
value.
