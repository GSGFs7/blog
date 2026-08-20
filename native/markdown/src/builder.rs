use markdown_it::MarkdownIt;

pub(crate) fn build() -> MarkdownIt {
    let mut inner = MarkdownIt::new();
    markdown_it::plugins::extra::front_matter::add(&mut inner);
    markdown_it::plugins::cmark::add(&mut inner);
    markdown_it::plugins::extra::tables::add(&mut inner);
    markdown_it::plugins::extra::strikethrough::add(&mut inner);
    markdown_it::plugins::extra::mark::add(&mut inner);
    markdown_it::plugins::extra::beautify_links::add(&mut inner);
    markdown_it::plugins::directives::add(&mut inner);
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
