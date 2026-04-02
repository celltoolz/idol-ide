from __future__ import annotations

_editor_keys_map = {
    "background": "bg",
    "foreground": "fg",
    "selectbackground": "select_bg",
    "selectforeground": "select_fg",
    "inactiveselectbackground": "inactive_select_bg",
    "insertbackground": "caret",
    "insertwidth": "caret_width",
    "borderwidth": "border_width",
    "highlightthickness": "focus_border_width",
}

_extras = {
    "Error": "error",
    "Literal.Date": "date",
}

_keywords = {
    "Keyword.Constant": "constant",
    "Keyword.Declaration": "declaration",
    "Keyword.Namespace": "namespace",
    "Keyword.Pseudo": "pseudo",
    "Keyword.Reserved": "reserved",
    "Keyword.Type": "type",
}

_names = {
    "Name.Attribute": "attr",
    "Name.Builtin": "builtin",
    "Name.Builtin.Pseudo": "builtin_pseudo",
    "Name.Class": "class",
    "Name.Constant": "constant",
    "Name.Decorator": "decorator",
    "Name.Entity": "entity",
    "Name.Exception": "exception",
    "Name.Function": "function",
    "Name.Function.Magic": "magic_function",
    "Name.Label": "label",
    "Name.Namespace": "namespace",
    "Name.Tag": "tag",
    "Name.Variable": "variable",
    "Name.Variable.Class": "class_variable",
    "Name.Variable.Global": "global_variable",
    "Name.Variable.Instance": "instance_variable",
    "Name.Variable.Magic": "magic_variable",
}

_strings = {
    "Literal.String.Affix": "affix",
    "Literal.String.Backtick": "backtick",
    "Literal.String.Char": "char",
    "Literal.String.Delimeter": "delimeter",
    "Literal.String.Doc": "doc",
    "Literal.String.Double": "double",
    "Literal.String.Escape": "escape",
    "Literal.String.Heredoc": "heredoc",
    "Literal.String.Interpol": "interpol",
    "Literal.String.Regex": "regex",
    "Literal.String.Single": "single",
    "Literal.String.Symbol": "symbol",
}

_numbers = {
    "Literal.Number.Bin": "binary",
    "Literal.Number.Float": "float",
    "Literal.Number.Hex": "hex",
    "Literal.Number.Integer": "integer",
    "Literal.Number.Integer.Long": "long",
    "Literal.Number.Oct": "octal",
}

_comments = {
    "Comment.Hashbang": "hashbang",
    "Comment.Multiline": "multiline",
    "Comment.Preproc": "preproc",
    "Comment.PreprocFile": "preprocfile",
    "Comment.Single": "single",
    "Comment.Special": "special",
}

_generic = {
    "Generic.Emph": "emphasis",
    "Generic.Error": "error",
    "Generic.Heading": "heading",
    "Generic.Strong": "strong",
    "Generic.Subheading": "subheading",
}


def _parse_table(
    source: dict[str, str | int] | None,
    map_: dict[str, str],
    fallback: str | int | None = None,
) -> dict[str, str | int | None]:
    result: dict[str, str | int | None] = {}
    if source is not None:
        for token, key in map_.items():
            result[token] = source.get(key, fallback)
    elif fallback is not None:
        for token in map_:
            result[token] = fallback
    return result


def _parse_scheme(color_scheme: dict[str, dict[str, str | int]]) -> tuple[dict, dict]:
    editor = {}
    if "editor" in color_scheme:
        editor_settings = color_scheme["editor"]
        for tk_name, key in _editor_keys_map.items():
            editor[tk_name] = editor_settings.get(key)

    assert "general" in color_scheme, "General table must be present in color scheme"
    general = color_scheme["general"]

    tags = {
        "Error": general.get("error"),
        "Escape": general.get("escape"),
        "Punctuation": general.get("punctuation"),
        "Comment": general.get("comment"),
        "Keyword": general.get("keyword"),
        "Keyword.Other": general.get("keyword"),
        "Literal.String": general.get("string"),
        "Literal.String.Other": general.get("string"),
        "Name.Other": general.get("name"),
    }

    tags.update(**_parse_table(color_scheme.get("keyword"), _keywords, general.get("keyword")))
    tags.update(**_parse_table(color_scheme.get("name"), _names, general.get("name")))
    tags.update(**_parse_table(color_scheme.get("operator"), {"Operator": "symbol", "Operator.Word": "word"}))
    tags.update(**_parse_table(color_scheme.get("string"), _strings, general.get("string")))
    tags.update(**_parse_table(color_scheme.get("number"), _numbers))
    tags.update(**_parse_table(color_scheme.get("comment"), _comments, general.get("comment")))
    tags.update(**_parse_table(color_scheme.get("generic"), _generic))
    tags.update(**_parse_table(color_scheme.get("extras"), _extras))

    return editor, tags
