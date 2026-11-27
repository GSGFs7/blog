//! HTML output helpers shared by the built-in HTML renderers.

use std::borrow::Cow;
use std::collections::HashMap;
use std::marker::PhantomData;

use super::{NodeRenderer, RenderContext, Writer};
use crate::document::{HtmlAttribute, Node, NodeValue};

/// Link-like payloads that render as `<a href="…">`.
///
/// Links from the CommonMark link rule, autolinks and linkify only differ in
/// where the destination comes from; the HTML output is identical.
pub(crate) trait LinkValue: NodeValue {
    fn href(&self) -> &str;

    /// Optional `title` attribute. Empty titles are omitted.
    fn title(&self) -> Option<&str> {
        None
    }
}

/// HTML renderer for any [`LinkValue`].
pub(crate) struct LinkHtmlRenderer<T>(PhantomData<fn() -> T>);

impl<T: LinkValue> LinkHtmlRenderer<T> {
    pub(crate) fn new() -> Self {
        Self(PhantomData)
    }
}

impl<T: LinkValue> NodeRenderer<T> for LinkHtmlRenderer<T> {
    fn render(&self, node: &Node, value: &T, context: &mut RenderContext<'_>, output: &mut Writer) {
        render_html_link(node, value.href(), value.title(), context, output);
    }
}

fn render_html_link(
    node: &Node,
    url: &str,
    title: Option<&str>,
    context: &mut RenderContext<'_>,
    output: &mut Writer,
) {
    let title = title.filter(|title| !title.is_empty());
    let extra = [("href", url), ("title", title.unwrap_or_default())];
    output.write_str("<a");
    write_html_attrs_with(
        output,
        node.attrs(),
        &extra[..1 + usize::from(title.is_some())],
    );
    output.write_char('>');
    context.render_children(node.id(), output);
    write_html_close(output, "a");
}

fn write_html_attrs(output: &mut Writer, attrs: &[HtmlAttribute]) {
    write_html_attrs_with(output, attrs, &[]);
}

/// Write attributes, merging same-named `class`/`style` values and keeping every
/// other duplicate as its own attribute.
///
/// Values in `extra` are appended after `attrs` without cloning either list.
pub(crate) fn write_html_attrs_with(
    output: &mut Writer,
    attrs: &[HtmlAttribute],
    extra: &[(&str, &str)],
) {
    /// Below this many attributes a linear scan beats building a map.
    const LINEAR_SCAN_LIMIT: usize = 8;

    let count = attrs.len() + extra.len();
    if count == 0 {
        return;
    }

    let attrs = attrs
        .iter()
        .map(|(name, value)| (name.as_str(), value.as_str()))
        .chain(extra.iter().copied());
    if count <= LINEAR_SCAN_LIMIT {
        // O(n^2), but with no allocation and a tiny `n`.
        for (index, (name, _)) in attrs.clone().enumerate() {
            let seen_before = attrs
                .clone()
                .take(index)
                .any(|(previous, _)| previous == name);
            if seen_before {
                continue;
            }

            write_html_attr_group(
                output,
                name,
                attrs
                    .clone()
                    .filter_map(|(candidate, value)| (candidate == name).then_some(value)),
            );
        }
        return;
    }

    // Large lists: group by name in one pass, remembering first-seen order.
    let mut values = HashMap::<&str, Vec<&str>>::new();
    let mut order = Vec::with_capacity(count);
    for (name, value) in attrs {
        values
            .entry(name)
            .or_insert_with(|| {
                order.push(name);
                Vec::new()
            })
            .push(value);
    }
    for name in order {
        if let Some(parts) = values.remove(name) {
            write_html_attr_group(output, name, parts.into_iter());
        }
    }
}

fn write_html_attr_group<'a>(
    output: &mut Writer,
    name: &str,
    values: impl Iterator<Item = &'a str>,
) {
    if name == "class" || name == "style" {
        output.write_char(' ');
        output.write_escaped_html(name);
        output.write_str("=\"");
        let separator = if name == "class" { ' ' } else { ';' };
        for (index, value) in values.enumerate() {
            if index != 0 {
                output.write_char(separator);
            }
            output.write_escaped_html(value);
        }
        output.write_char('"');
    } else {
        for value in values {
            output.write_char(' ');
            output.write_escaped_html(name);
            output.write_str("=\"");
            output.write_escaped_html(value);
            output.write_char('"');
        }
    }
}

pub(crate) fn write_html_open(output: &mut Writer, tag: &str, attrs: &[HtmlAttribute]) {
    output.write_char('<');
    output.write_str(tag);
    write_html_attrs(output, attrs);
    output.write_char('>');
}

pub(crate) fn write_html_close(output: &mut Writer, tag: &str) {
    output.write_str("</");
    output.write_str(tag);
    output.write_char('>');
}

pub(crate) fn write_html_self_close(
    output: &mut Writer,
    tag: &str,
    attrs: &[HtmlAttribute],
    xhtml: bool,
) {
    output.write_char('<');
    output.write_str(tag);
    write_html_attrs(output, attrs);
    if xhtml {
        output.write_str(" /");
    }
    output.write_char('>');
}

pub(crate) fn write_html_text(output: &mut Writer, value: &str) {
    output.write_escaped_html(value);
}

/// Escape `" < > &` with corresponding HTML entities.
/// ```
/// # use markdown_it::render::escape_html;
/// assert_eq!(escape_html("&\""), "&amp;&quot;");
/// ```
pub fn escape_html(str: &str) -> Cow<'_, str> {
    let Some(first) = find_first_html_escape(str.as_bytes()) else {
        return Cow::Borrowed(str);
    };

    // '"' -> "&quot;"
    let mut output = String::with_capacity(str.len() + 5);
    push_escaped_html_from(str, first, &mut output);
    Cow::Owned(output)
}

/// Append `str` into `output` with HTML special characters escaped, without
/// allocating an intermediate `String`.
#[inline]
pub(crate) fn write_escaped_html_to(str: &str, output: &mut String) {
    let Some(first) = find_first_html_escape(str.as_bytes()) else {
        output.push_str(str);
        return;
    };

    output.reserve(str.len() + 5);
    push_escaped_html_from(str, first, output);
}

#[inline]
fn find_first_html_escape(bytes: &[u8]) -> Option<usize> {
    if bytes.len() < 32 {
        bytes
            .iter()
            .position(|b| matches!(b, b'&' | b'<' | b'>' | b'"'))
    } else {
        let other = memchr::memchr3(b'&', b'<', b'>', bytes).unwrap_or(bytes.len());
        memchr::memchr(b'"', &bytes[..other]).or_else(|| (other < bytes.len()).then_some(other))
    }
}

fn push_escaped_html_from(str: &str, first: usize, output: &mut String) {
    output.push_str(&str[..first]);

    let mut start = first;
    for (offset, byte) in str[first..].bytes().enumerate() {
        let index = first + offset;
        macro_rules! append_escape {
            ($entity:literal) => {{
                if start != index {
                    output.push_str(&str[start..index]);
                }
                output.push_str($entity);
                start = index + 1;
            }};
        }
        match byte {
            b'&' => append_escape!("&amp;"),
            b'<' => append_escape!("&lt;"),
            b'>' => append_escape!("&gt;"),
            b'"' => append_escape!("&quot;"),
            _ => {}
        }
    }

    output.push_str(&str[start..]);
}

#[cfg(test)]
mod tests {
    use super::write_html_attrs;
    use crate::render::Writer;

    #[test]
    fn html_attrs_preserve_grouping_order_and_escaping_on_both_paths() {
        let small = vec![
            ("class".into(), "first".into()),
            ("id".into(), "one".into()),
            ("class".into(), "second".into()),
            ("style".into(), "color:<red>".into()),
            ("title".into(), "<&>".into()),
            ("style".into(), "display:block".into()),
            ("id".into(), "two".into()),
        ];
        let mut output = Writer::new();
        write_html_attrs(&mut output, &small);
        assert_eq!(
            output.finish(),
            " class=\"first second\" id=\"one\" id=\"two\" style=\"color:&lt;red&gt;;display:block\" title=\"&lt;&amp;&gt;\""
        );

        let mut large = small;
        large.extend([("data-a".into(), "a".into()), ("data-b".into(), "b".into())]);
        let mut output = Writer::new();
        write_html_attrs(&mut output, &large);
        assert_eq!(
            output.finish(),
            " class=\"first second\" id=\"one\" id=\"two\" style=\"color:&lt;red&gt;;display:block\" title=\"&lt;&amp;&gt;\" data-a=\"a\" data-b=\"b\""
        );
    }
}
