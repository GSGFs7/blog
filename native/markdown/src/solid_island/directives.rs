use markdown_it::MarkdownIt;
use markdown_it::plugins::directives::{self, DirectiveKind, DirectiveNode, DirectiveRenderer};
use markdown_it::render::escape_html;

use super::component::Component;

pub(crate) fn add(md: &mut MarkdownIt) {
    for &name in Component::ALL
        .iter()
        .flat_map(|component| component.aliases())
    {
        for kind in [
            DirectiveKind::Text,
            DirectiveKind::Leaf,
            DirectiveKind::Container,
        ] {
            directives::add_render(md, kind, name, render);
        }
    }
}

fn render(
    kind: DirectiveKind,
    name: &str,
    attrs: &[(String, String)],
    node: DirectiveNode<'_>,
    fmt: &mut DirectiveRenderer<'_, '_>,
) {
    let component = Component::from_directive(name).expect("registered Solid directive");
    let props = component.props_json(
        node.attrs()
            .iter()
            .chain(attrs)
            .map(|(name, value)| (name.clone(), escape_html(value).into_owned())),
    );
    let block = kind != DirectiveKind::Text;
    let tag = if block { "div" } else { "span" };

    if block {
        fmt.cr();
    }
    fmt.text_raw(&format!(
        "<{tag} data-solid-island=\"{}\" data-props=\"{}\">",
        component.name(),
        escape_html(&props),
    ));
    if let Some(placeholder) = component.placeholder() {
        fmt.text_raw(placeholder);
    } else {
        fmt.contents(node.children());
    }
    fmt.close(tag);
    if block {
        fmt.cr();
    }
}
