use markdown_it::MarkdownIt;
use markdown_it::plugins::directives::DirectiveKind;

use crate::spoiler::render_spoiler;
use crate::terminal::render_terminal;

pub(crate) fn build() -> MarkdownIt {
    let mut inner = build_common();
    markdown_it::plugins::extra::syntect::add(&mut inner);
    markdown_it::plugins::extra::syntect::set_to_classed(&mut inner);
    inner
}

pub(crate) fn build_text() -> MarkdownIt {
    build_common()
}

fn build_common() -> MarkdownIt {
    let mut inner = MarkdownIt::empty();
    markdown_it::plugins::cmark::add(&mut inner);
    markdown_it::plugins::extra::front_matter::add(&mut inner);
    markdown_it::plugins::extra::tables::add(&mut inner);
    markdown_it::plugins::extra::strikethrough::add(&mut inner);
    markdown_it::plugins::extra::mark::add(&mut inner);
    markdown_it::plugins::extra::beautify_links::add(&mut inner);
    markdown_it::plugins::extra::tasklist::add(&mut inner);
    markdown_it::plugins::extra::footnote::add(&mut inner);
    markdown_it::plugins::extra::heading_anchors::add(&mut inner);
    markdown_it::plugins::extra::linkify::add(&mut inner);
    markdown_it::plugins::extra::math::add(&mut inner);
    markdown_it::plugins::html::add(&mut inner);
    markdown_it::plugins::directives::add(&mut inner);
    markdown_it::plugins::directives::add_render(
        &mut inner,
        DirectiveKind::Container,
        "spoiler",
        render_spoiler,
    );
    markdown_it::plugins::directives::add_render(
        &mut inner,
        DirectiveKind::Leaf,
        "terminal",
        render_terminal,
    );
    markdown_it::plugins::directives::add_render(
        &mut inner,
        DirectiveKind::Container,
        "terminal",
        render_terminal,
    );
    crate::solid_island::add(&mut inner);
    inner
}
