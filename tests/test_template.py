from context_agent.template import assemble_document, split_template


def test_split_template_uses_first_effective_pair() -> None:
    source = r"""
% \starttext in a comment
\starttyping
\starttext
\stoptext
\stoptyping
\setupbodyfont[modern]
\starttext
real body
\stoptext
trailing ideas
\stoptext
"""
    parts = split_template(source)
    assert "setupbodyfont" in parts.preamble
    assert "real body" in parts.body
    assert "trailing ideas" in parts.trailing


def test_assemble_document_discards_trailing_material() -> None:
    source = assemble_document("\\setupbodyfont[modern]", "Neue Aufgabe")
    assert source.count("\\starttext") == 1
    assert source.count("\\stoptext") == 1
    assert "Neue Aufgabe" in source
