use markdown_it::plugins::directives::DirectiveKind;
use markdown_it::{MarkdownIt, Node, Renderer};

// REFAC: move this to somewhere else
fn render_spoiler(
    _kind: DirectiveKind,
    _name: &str,
    attrs: &[(String, String)],
    node: &Node,
    fmt: &mut dyn Renderer,
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

    fmt.contents(&node.children);

    fmt.close("details");
    fmt.cr();
}

pub(crate) fn build() -> MarkdownIt {
    let mut inner = MarkdownIt::empty();
    markdown_it::plugins::extra::front_matter::add(&mut inner);
    markdown_it::plugins::cmark::add(&mut inner);
    markdown_it::plugins::extra::tables::add(&mut inner);
    markdown_it::plugins::extra::strikethrough::add(&mut inner);
    markdown_it::plugins::extra::mark::add(&mut inner);
    markdown_it::plugins::extra::beautify_links::add(&mut inner);
    markdown_it::plugins::directives::add(&mut inner);
    markdown_it::plugins::directives::add_render(
        &mut inner,
        DirectiveKind::Container,
        "spoiler",
        render_spoiler,
    );
    markdown_it::plugins::extra::tasklist::add(&mut inner);
    markdown_it::plugins::extra::footnote::add(&mut inner);
    markdown_it::plugins::extra::heading_anchors::add(&mut inner);
    markdown_it::plugins::html::add(&mut inner);
    markdown_it::plugins::extra::linkify::add(&mut inner);
    markdown_it::plugins::extra::math::add(&mut inner);
    markdown_it::plugins::extra::syntect::add(&mut inner);
    markdown_it::plugins::extra::syntect::set_to_classed(&mut inner);
    inner
}
