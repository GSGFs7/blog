use std::collections::HashMap;

use crate::render::{Writer, write_escaped_html_to};

const INLINE_TAG_COPY: usize = 24;
const INLINE_ATTR_CAPACITY: usize = 12; // 12 works very well on my machine

/// Streaming HTML fragment builder passed to high-level renderers.
///
/// Writes escaped text and markup into the renderer's output buffer.
#[derive(Debug)]
pub struct Html {
    output: Writer,
    xhtml_out: bool,
    pending_child: Option<usize>,
}

impl Html {
    /// Add a child element.
    ///
    /// The element is closed when it is dropped at the end of the statement:
    /// ```ignore
    /// html.element("span").class("emoji").text("🚀");
    /// ```
    ///
    /// # Panics
    ///
    /// Panics if `tag` is not a valid ASCII HTML tag name.
    #[inline]
    pub fn element(&mut self, tag: impl AsRef<str>) -> HtmlElement<'_> {
        HtmlElement::new(
            &mut self.output,
            &mut self.pending_child,
            self.xhtml_out,
            tag.as_ref(),
        )
    }

    /// Append text. It is HTML-escaped directly into the output buffer.
    #[inline]
    pub fn text(&mut self, text: impl AsRef<str>) -> &mut Self {
        discard_pending_child(&mut self.output, &mut self.pending_child);
        self.output.write_escaped_html(text.as_ref());
        self
    }

    /// Append markup verbatim. The caller is responsible for escaping it.
    #[inline]
    pub fn raw(&mut self, html: impl AsRef<str>) -> &mut Self {
        discard_pending_child(&mut self.output, &mut self.pending_child);
        self.output.write_str(html.as_ref());
        self
    }
}

#[inline]
pub(super) fn render_html_fragment(
    render: impl FnOnce(&mut Html),
    xhtml_out: bool,
    output: &mut Writer,
) {
    let fragment_start = output.len();
    let html = Html {
        output: std::mem::take(output),
        xhtml_out,
        pending_child: None,
    };
    let mut guard = HtmlOutputGuard {
        target: output,
        html,
        fragment_start,
        complete: false,
    };
    render(&mut guard.html);
    discard_pending_child(&mut guard.html.output, &mut guard.html.pending_child);
    guard.complete = true;
}

/// Restores the writer to its original owner and rolls back an aborted callback.
struct HtmlOutputGuard<'a> {
    target: &'a mut Writer,
    html: Html,
    fragment_start: usize,
    complete: bool,
}

impl Drop for HtmlOutputGuard<'_> {
    #[inline]
    fn drop(&mut self) {
        if !self.complete {
            self.html
                .output
                .as_mut_string()
                .truncate(self.fragment_start);
        }
        *self.target = std::mem::take(&mut self.html.output);
    }
}

/// An element clears its parent's checkpoint when it closes. A checkpoint
/// still present when the parent resumes marks an unfinished child.
#[inline]
fn discard_pending_child(output: &mut Writer, pending_child: &mut Option<usize>) {
    if let Some(start) = pending_child.take() {
        output.as_mut_string().truncate(start);
    }
}

/// One element under construction.
///
/// Chained calls return `&mut Self`, and the closing tag is emitted when the
/// value is dropped.
#[derive(Debug)]
pub struct HtmlElement<'a> {
    output: &'a mut Writer,
    parent_pending_child: &'a mut Option<usize>,
    pending_child: Option<usize>,
    xhtml_out: bool,
    /// Byte range of the tag name already written to the buffer.
    tag_start: usize,
    tag_len: usize,
    /// End of the attributes already written to the buffer.
    attrs_end: usize,
    inline_attrs: [AttrSpan; INLINE_ATTR_CAPACITY],
    inline_attr_count: usize,
    buffered_attrs: Option<Box<BufferedAttrs>>,
    open_tag_closed: bool,
    void: bool,
}

impl<'a> HtmlElement<'a> {
    #[inline]
    fn new(
        output: &'a mut Writer,
        parent_pending_child: &'a mut Option<usize>,
        xhtml_out: bool,
        tag: &str,
    ) -> Self {
        validate_tag(tag);
        discard_pending_child(output, parent_pending_child);
        let buf = output.as_mut_string();
        *parent_pending_child = Some(buf.len());
        buf.reserve(tag.len() + 2);
        buf.push('<');
        let tag_start = buf.len();
        buf.push_str(tag);
        let attrs_end = buf.len();

        Self {
            output,
            parent_pending_child,
            pending_child: None,
            xhtml_out,
            tag_start,
            tag_len: tag.len(),
            attrs_end,
            inline_attrs: [AttrSpan::default(); INLINE_ATTR_CAPACITY],
            inline_attr_count: 0,
            buffered_attrs: None,
            open_tag_closed: false,
            void: false,
        }
    }

    #[inline]
    fn prepare_child(&mut self) {
        discard_pending_child(self.output, &mut self.pending_child);
        if !self.open_tag_closed {
            self.output.write_char('>');
            self.open_tag_closed = true;
        }
    }

    /// Add an attribute. Its value is HTML-escaped, and the name must be a valid
    /// HTML attribute name.
    ///
    /// Repeated `class` and `style` attributes are merged (separated by `' '`
    /// and `';'`); other duplicate attributes are grouped next to their first
    /// occurrence, matching the built-in HTML renderer.
    ///
    /// # Panics
    ///
    /// Panics if `name` is not a valid HTML attribute name.
    #[inline]
    pub fn attr(&mut self, name: impl AsRef<str>, value: impl AsRef<str>) -> &mut Self {
        let name = name.as_ref();
        let value = value.as_ref();
        validate_attr_name(name);
        discard_pending_child(self.output, &mut self.pending_child);

        if let Some(attrs) = &mut self.buffered_attrs {
            attrs.push(name, value);
        } else if self.open_tag_closed {
            self.buffer_attr(name, value);
        } else {
            let spans = &self.inline_attrs[..self.inline_attr_count];
            let output = self.output.as_str();
            let existing = spans
                .iter()
                .position(|span| &output[span.name_start..span.name_start + span.name_len] == name);

            if existing.is_none() && self.inline_attr_count < INLINE_ATTR_CAPACITY {
                let span = append_attr(self.output.as_mut_string(), name, value);
                self.attrs_end = span.end;
                self.inline_attrs[self.inline_attr_count] = span;
                self.inline_attr_count += 1;
            } else if let Some(index) = existing
                && index + 1 == self.inline_attr_count
                && let Some(separator) = attr_separator(name)
            {
                let buf = self.output.as_mut_string();
                append_merged_value(buf, separator, value);
                self.attrs_end = buf.len();
                self.inline_attrs[index].end = self.attrs_end;
            } else {
                self.buffer_attr(name, value);
            }
        }
        self
    }

    /// Copy the small prefix of attributes once, then group new values without
    /// modifying the output until the element closes.
    #[cold]
    fn buffer_attr(&mut self, name: &str, value: &str) {
        let mut attrs = Box::<BufferedAttrs>::default();
        let output = self.output.as_str();
        for span in &self.inline_attrs[..self.inline_attr_count] {
            let attr_name = &output[span.name_start..span.name_start + span.name_len];
            attrs
                .indexes
                .insert(attr_name.to_owned(), attrs.groups.len());
            attrs
                .groups
                .push(output[span.name_start - 1..span.end].to_owned());
        }
        attrs.push(name, value);
        self.buffered_attrs = Some(attrs);
    }

    /// Add a `class` attribute.
    #[inline]
    pub fn class(&mut self, class: impl AsRef<str>) -> &mut Self {
        self.attr("class", class)
    }

    /// Mark this element as void, e.g. `<img>` or `<br>`.
    #[inline]
    pub fn void(&mut self) -> &mut Self {
        self.void = true;
        self
    }

    /// Add a child element.
    ///
    /// # Panics
    ///
    /// Panics if `tag` is not a valid ASCII HTML tag name.
    #[inline]
    pub fn element(&mut self, tag: impl AsRef<str>) -> HtmlElement<'_> {
        self.prepare_child();
        HtmlElement::new(
            self.output,
            &mut self.pending_child,
            self.xhtml_out,
            tag.as_ref(),
        )
    }

    /// Append text. It is HTML-escaped directly into the output buffer.
    #[inline]
    pub fn text(&mut self, text: impl AsRef<str>) -> &mut Self {
        self.prepare_child();
        self.output.write_escaped_html(text.as_ref());
        self
    }

    /// Append markup verbatim. The caller is responsible for escaping it.
    #[inline]
    pub fn raw(&mut self, html: impl AsRef<str>) -> &mut Self {
        self.prepare_child();
        self.output.write_str(html.as_ref());
        self
    }
}

impl Drop for HtmlElement<'_> {
    #[inline]
    fn drop(&mut self) {
        discard_pending_child(self.output, &mut self.pending_child);
        let buf = self.output.as_mut_string();
        let tag_end = self.tag_start + self.tag_len;

        if self.void {
            buf.truncate(self.attrs_end);
        }
        if let Some(attrs) = self.buffered_attrs.take() {
            if self.open_tag_closed && !self.void {
                buf.replace_range(tag_end..self.attrs_end, &attrs.finish());
            } else {
                buf.truncate(tag_end);
                for group in attrs.groups {
                    buf.push_str(&group);
                }
            }
        }
        if self.void {
            if self.xhtml_out {
                buf.push_str(" />");
            } else {
                buf.push('>');
            }
        } else {
            buf.reserve(self.tag_len + 4);
            if !self.open_tag_closed {
                buf.push('>');
            }
            buf.push_str("</");
            if self.tag_len <= INLINE_TAG_COPY {
                let mut tmp = [0u8; INLINE_TAG_COPY];
                tmp[..self.tag_len].copy_from_slice(&buf.as_bytes()[self.tag_start..tag_end]);
                // `validate_tag` guarantees ASCII bytes.
                let tag = std::str::from_utf8(&tmp[..self.tag_len])
                    .expect("validated ASCII HTML tag name");
                buf.push_str(tag);
            } else {
                let tag = buf[self.tag_start..tag_end].to_owned();
                buf.push_str(&tag);
            }
            buf.push('>');
        }
        *self.parent_pending_child = None;
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct AttrSpan {
    name_start: usize,
    name_len: usize,
    end: usize,
}

#[derive(Debug, Default)]
struct BufferedAttrs {
    indexes: HashMap<String, usize>,
    groups: Vec<String>,
}

impl BufferedAttrs {
    fn push(&mut self, name: &str, value: &str) {
        if let Some(&index) = self.indexes.get(name) {
            let group = &mut self.groups[index];
            if let Some(separator) = attr_separator(name) {
                append_merged_value(group, separator, value);
            } else {
                append_attr(group, name, value);
            }
        } else {
            let mut group = String::new();
            append_attr(&mut group, name, value);
            self.indexes.insert(name.to_owned(), self.groups.len());
            self.groups.push(group);
        }
    }

    fn finish(self) -> String {
        let mut attrs = String::with_capacity(self.groups.iter().map(String::len).sum());
        for group in self.groups {
            attrs.push_str(&group);
        }
        attrs
    }
}

// --- helper ---

#[inline]
fn append_attr(buf: &mut String, name: &str, value: &str) -> AttrSpan {
    buf.reserve(name.len() + value.len() + 4);
    buf.push(' ');
    let name_start = buf.len();
    buf.push_str(name);
    buf.push_str("=\"");
    write_escaped_html_to(value, buf);
    buf.push('"');
    AttrSpan {
        name_start,
        name_len: name.len(),
        end: buf.len(),
    }
}

#[inline]
fn attr_separator(name: &str) -> Option<char> {
    match name {
        "class" => Some(' '),
        "style" => Some(';'),
        _ => None,
    }
}

#[inline]
fn append_merged_value(buf: &mut String, separator: char, value: &str) {
    debug_assert_eq!(buf.as_bytes().last(), Some(&b'"'));
    buf.pop();
    buf.reserve(value.len() + 2);
    buf.push(separator);
    write_escaped_html_to(value, buf);
    buf.push('"');
}

#[inline]
pub(super) fn validate_tag(tag: &str) {
    const VALID_TAG_BYTES: [bool; 256] = {
        let mut table = [false; 256];
        let mut i = 0;
        while i < 256 {
            let b = i as u8;
            table[i] = b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b':');
            i += 1;
        }
        table
    };

    assert!(
        !tag.is_empty() && tag.bytes().all(|b| VALID_TAG_BYTES[usize::from(b)]),
        "invalid HTML tag name: {tag:?}"
    );
}

#[inline]
fn validate_attr_name(name: &str) {
    const VALID_ATTR_BYTES: [bool; 256] = {
        let mut table = [false; 256];
        let mut i = 0;
        while i < 256 {
            let b = i as u8;
            table[i] =
                b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b':' | b'.' | b'@' | b'#');
            i += 1;
        }
        table
    };

    assert!(
        !name.is_empty() && name.bytes().all(|b| VALID_ATTR_BYTES[usize::from(b)]),
        "invalid HTML attribute name: {name:?}"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    fn render_fragment(xhtml_out: bool, f: impl FnOnce(&mut Html)) -> String {
        let mut out = Writer::new();
        render_html_fragment(f, xhtml_out, &mut out);
        out.finish()
    }

    #[test]
    fn merges_duplicate_class_style_and_groups_other_attributes_in_all_orders() {
        let rendered = render_fragment(false, |html| {
            html.element("div")
                .class("first")
                .attr("id", "one")
                .class("second")
                .attr("style", "color:<red>")
                .attr("title", "<&>")
                .attr("style", "display:block")
                .attr("id", "two")
                .text("body")
                .class("third")
                .attr("id", "three")
                .attr("data-late", "\"q\"");
        });
        assert_eq!(
            rendered,
            "<div class=\"first second third\" id=\"one\" id=\"two\" id=\"three\" style=\"color:&lt;red&gt;;display:block\" title=\"&lt;&amp;&gt;\" data-late=\"&quot;q&quot;\">body</div>"
        );
    }

    #[test]
    fn handles_many_attributes_and_long_tag_names() {
        let long_tag = "custom-very-long-html-element-name-exceeding-inline-buffer";
        let rendered = render_fragment(false, |html| {
            let mut el = html.element(long_tag);
            for i in 0..=INLINE_ATTR_CAPACITY {
                el.attr(format!("data-k{i}"), format!("v{i}"));
            }
            el.class("a")
                .class("b")
                .attr("data-k0", "v0-dup")
                .text("ok");
        });
        assert!(rendered.starts_with(&format!(
            "<{long_tag} data-k0=\"v0\" data-k0=\"v0-dup\" data-k1=\"v1\""
        )));
        assert!(rendered.contains(" class=\"a b\""));
        assert!(rendered.ends_with(&format!(">ok</{long_tag}>")));
    }

    #[test]
    fn many_late_attributes_match_builtin_grouping_and_escaping() {
        let mut attrs = vec![
            ("class".to_owned(), "<&".to_owned()),
            ("class".to_owned(), "\"".to_owned()),
            ("title".to_owned(), "你好".to_owned()),
        ];
        for i in 0..128 {
            attrs.push((format!("data-k{i}"), format!("v&{i}")));
        }
        attrs.extend([
            ("class".to_owned(), ">".to_owned()),
            ("title".to_owned(), "second".to_owned()),
            ("style".to_owned(), "color:red".to_owned()),
            ("style".to_owned(), "display:block".to_owned()),
        ]);

        let body = "正文<&".repeat(256);
        let rendered = render_fragment(false, |html| {
            let mut el = html.element("div");
            for (name, value) in &attrs[..3] {
                el.attr(name, value);
            }
            el.text(&body);
            for (name, value) in &attrs[3..] {
                el.attr(name, value);
            }
        });

        let mut expected = Writer::new();
        crate::render::write_html_open(&mut expected, "div", &attrs);
        expected.write_escaped_html(&body);
        expected.write_str("</div>");
        assert_eq!(rendered, expected.finish());
    }

    #[test]
    fn void_element_supports_late_void_and_xhtml_out() {
        for xhtml_out in [false, true] {
            let suffix = if xhtml_out { " />" } else { ">" };
            let rendered = render_fragment(xhtml_out, |html| {
                html.element("img")
                    .attr("src", "a.png")
                    .text("ignored")
                    .void()
                    .attr("alt", "x");
            });
            assert_eq!(rendered, format!("<img src=\"a.png\" alt=\"x\"{suffix}"));
        }
    }

    #[test]
    fn preserves_existing_output_prefix_and_nested_late_attrs() {
        let mut out = Writer::new();
        out.write_str("prefix:");
        render_html_fragment(
            |html| {
                let mut outer = html.element("div");
                outer.class("a");
                outer.element("span").class("inner").text("hi");
                outer.class("b");
            },
            false,
            &mut out,
        );
        out.write_str(":suffix");
        assert_eq!(
            out.finish(),
            "prefix:<div class=\"a b\"><span class=\"inner\">hi</span></div>:suffix"
        );
    }

    #[test]
    fn empty_class_and_adjacent_duplicate_class_merge_identically() {
        let rendered = render_fragment(false, |html| {
            html.element("span").class("").class("a").class("b");
        });
        assert_eq!(rendered, "<span class=\" a b\"></span>");
    }

    #[test]
    fn discards_unfinished_elements_before_siblings_and_at_fragment_end() {
        let rendered = render_fragment(false, |html| {
            html.text("前");
            let mut unfinished = html.element("span");
            unfinished.element("b").text("discarded");
            std::mem::forget(unfinished);
            html.text("after");

            {
                let mut outer = html.element("div");
                std::mem::forget(outer.element("span"));
                outer.class("late");
                outer.element("b").text("kept");
                std::mem::forget(outer.element("em"));
            }
            std::mem::forget(html.element("br"));
        });
        assert_eq!(rendered, "前after<div class=\"late\"><b>kept</b></div>");
    }

    #[test]
    fn aborted_fragment_restores_existing_output() {
        let mut out = Writer::new();
        out.write_str("前:");
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            render_html_fragment(
                |html| {
                    html.raw("<b>partial</b>");
                    let mut element = html.element("em");
                    element.text("partial").class("late");
                    panic!("fallback");
                },
                false,
                &mut out,
            );
        }));
        assert!(result.is_err());
        render_html_fragment(
            |html| {
                html.text("fallback");
            },
            false,
            &mut out,
        );
        assert_eq!(out.finish(), "前:fallback");
    }

    #[test]
    #[should_panic(expected = "invalid HTML tag name")]
    fn rejects_invalid_tag_name() {
        render_fragment(false, |html| {
            html.element("bad tag");
        });
    }

    #[test]
    #[should_panic(expected = "invalid HTML attribute name")]
    fn rejects_invalid_attr_name() {
        render_fragment(false, |html| {
            html.element("span").attr("bad name", "1");
        });
    }
}
