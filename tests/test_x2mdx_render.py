from x2mdx.output import Page, RawMarkdown
from x2mdx.render import render_page


def test_render_page_strips_trailing_whitespace() -> None:
    rendered = render_page(
        Page(
            path="example.mdx",
            title="Example",
            blocks=[RawMarkdown("<div>\n  \n  <p>Text</p>  \n</div>")],
        )
    )

    assert "\n  \n" not in rendered
    assert "<p>Text</p>  " not in rendered
    assert rendered.endswith("</div>\n")


def test_render_page_supports_manual_api_frontmatter() -> None:
    rendered = render_page(
        Page(
            path="create.mdx",
            title="Create a payment",
            frontmatter={
                "api": "POST http://localhost:7575/v2/payments",
                "authMethod": "bearer",
                "playground": "interactive",
            },
        )
    )

    assert 'api: "POST http://localhost:7575/v2/payments"' in rendered
    assert 'authMethod: "bearer"' in rendered
    assert 'playground: "interactive"' in rendered


def test_render_page_rejects_duplicate_reserved_frontmatter() -> None:
    page = Page(path="example.mdx", title="Example", frontmatter={"title": "Duplicate"})

    try:
        render_page(page)
    except ValueError as error:
        assert str(error) == "Reserved frontmatter key: title"
    else:
        raise AssertionError("Expected duplicate title metadata to fail")
