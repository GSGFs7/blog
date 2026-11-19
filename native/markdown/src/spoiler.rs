use markdown_it::MarkdownIt;
use markdown_it::document::Node;
use markdown_it::parser::inline::helpers::emph_pair;
use markdown_it::plugins::directives::{DirectiveKind, DirectiveNode, DirectiveRenderer};
use markdown_it::render::{NodeRenderer, RenderContext, Writer};

#[derive(Debug)]
struct InlineSpoiler;

struct InlineSpoilerRenderer;

impl NodeRenderer<InlineSpoiler> for InlineSpoilerRenderer {
    fn render(
        &self,
        node: &Node,
        _: &InlineSpoiler,
        context: &mut RenderContext<'_>,
        output: &mut Writer,
    ) {
        output.write_str("<span class=\"heimu\">");
        context.render_children(node.id(), output);
        output.write_str("</span>");
    }
}

pub(crate) fn add_inline(md: &mut MarkdownIt) {
    emph_pair::add_with::<'|', 2, true>(md, |document| document.create_node(InlineSpoiler));
    md.add_renderer::<InlineSpoiler, _>("html", InlineSpoilerRenderer);
}

pub(crate) fn render_spoiler(
    _kind: DirectiveKind,
    _name: &str,
    attrs: &[(String, String)],
    node: DirectiveNode<'_>,
    fmt: &mut DirectiveRenderer<'_, '_>,
) {
    let title = attrs
        .iter()
        .find_map(|(key, value)| (key == "title").then_some(value.as_str()))
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("spoiler");

    fmt.cr();
    fmt.open("details", &[("class".into(), "spoiler".to_owned())]);

    fmt.open("summary", &[]);
    fmt.text(title);
    fmt.close("summary");

    fmt.cr();

    fmt.contents(node.children());

    fmt.close("details");
    fmt.cr();
}

#[cfg(test)]
mod tests {
    use crate::builder::{build, build_text};
    use crate::sanitizer::sanitize;

    #[test]
    fn renders_inline_spoilers() {
        let parser = build();
        for (source, expected) in [
            (
                "前||结局||后",
                "<p>前<span class=\"heimu\">结局</span>后</p>\n",
            ),
            (
                "||**粗体**与*斜体*||",
                "<p><span class=\"heimu\"><strong>粗体</strong>与<em>斜体</em></span></p>\n",
            ),
            (
                "||一||、||二||",
                "<p><span class=\"heimu\">一</span>、<span class=\"heimu\">二</span></p>\n",
            ),
            (
                "||a & <b>内容</b>||",
                "<p><span class=\"heimu\">a &amp; <b>内容</b></span></p>\n",
            ),
        ] {
            let html = parser.render(source);
            assert_eq!(html, expected, "{source}");
            assert_eq!(sanitize(&html), expected, "{source}");
        }
    }

    #[test]
    fn preserves_literal_pipes_and_code() {
        let parser = build_text();
        for (source, expected) in [
            (r"\|\|内容\|\|", "<p>||内容||</p>\n"),
            ("`||内容||`", "<p><code>||内容||</code></p>\n"),
            ("```\n||内容||\n```", "<pre><code>||内容||\n</code></pre>\n"),
            ("||未闭合", "<p>||未闭合</p>\n"),
            ("单|竖线|", "<p>单|竖线|</p>\n"),
            ("|| 内容 ||", "<p>|| 内容 ||</p>\n"),
        ] {
            assert_eq!(parser.render(source), expected, "{source}");
        }
    }

    #[test]
    fn renders_spoilers_inside_table_cells_with_escaped_pipes() {
        let html = build().render("| 标题 |\n| --- |\n| \\|\\|结局\\|\\| |");
        assert!(
            html.contains("<td><span class=\"heimu\">结局</span></td>"),
            "{html}"
        );
    }
}
