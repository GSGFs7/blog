use markdown_it::plugins::directives::{DirectiveKind, DirectiveNode, DirectiveRenderer};

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
