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
