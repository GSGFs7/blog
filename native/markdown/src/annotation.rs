use markdown_it::common::utils::unescape_all;
use markdown_it::parser::inline::helpers::paired_span::{
    self, EscapePolicy, NestingPolicy, PairOptions,
};
use markdown_it::plugin::PluginSpec;

#[derive(Debug)]
struct Annotation {
    description: String,
}

pub(crate) fn plugin() -> PluginSpec {
    let label = PairOptions::new("[", "]")
        .escape(EscapePolicy::Backslash)
        .nesting(NestingPolicy::SamePair)
        .allow_empty(false);
    let note = PairOptions::new("{", "}")
        .escape(EscapePolicy::Backslash)
        .nesting(NestingPolicy::SamePair)
        .allow_empty(false);

    PluginSpec::new("annotation")
        .inline_container::<Annotation>("annotation")
        .marker('[')
        .parse(move |cx| {
            cx.consume_part(&label)?;
            let matched = paired_span::scan(cx.remaining(), &note)?;
            let description = unescape_all(cx.remaining_slice(matched.body)?).into_owned();
            if description.trim().is_empty() || !cx.advance_bytes(matched.consumed) {
                return None;
            }
            Some(Annotation { description })
        })
        .render_html(|note, html| {
            let label = html.render_part(0);
            html.element("span")
                .class("md-note")
                .attr("data-note", &note.description)
                .attr("title", &note.description)
                .attr("tabindex", "0")
                .raw(label);
        })
        .finish()
}

#[cfg(test)]
mod tests {
    use crate::builder::build_text;
    use crate::sanitizer::sanitize;

    #[test]
    fn renders_markdown_labels_and_escaped_plain_text_descriptions() {
        let parser = build_text();
        for (source, label, description) in [
            ("[**文字**]{说明}", "<strong>文字</strong>", "说明"),
            (
                "[包含 `]` 的文字]{说明}",
                "包含 <code>]</code> 的文字",
                "说明",
            ),
            (
                "[包含 ``a`]b`` 的文字]{说明}",
                "包含 <code>a`]b</code> 的文字",
                "说明",
            ),
            (r"[文\]字]{说明\}与{括号}}", "文]字", "说明}与{括号}"),
            (
                "[文字]{\"<&amp; **纯文本**}",
                "文字",
                "&quot;&lt;&amp; **纯文本**",
            ),
            ("[包含[括号]的文字]{说明}", "包含[括号]的文字", "说明"),
        ] {
            let expected = format!(
                "<p><span class=\"md-note\" data-note=\"{description}\" title=\"{description}\" tabindex=\"0\">{label}</span></p>\n"
            );
            let html = parser.render(source);
            assert_eq!(html, expected, "{source}");
            assert_eq!(sanitize(&html), expected, "{source}");
            assert!(
                !crate::text::extract(&parser.parse(source))
                    .unwrap()
                    .contains("说明")
            );
        }
    }

    #[test]
    fn preserves_nested_annotations_links_and_literal_description_boundaries() {
        let parser = build_text();
        for (source, expected, text) in [
            (
                "[外[**内**]{内说明}层]{外说明}",
                "<p><span class=\"md-note\" data-note=\"外说明\" title=\"外说明\" tabindex=\"0\">外<span class=\"md-note\" data-note=\"内说明\" title=\"内说明\" tabindex=\"0\"><strong>内</strong></span>层</span></p>\n",
                "外内层",
            ),
            (
                "[[链接](https://example.com)]{说明}",
                "<p><span class=\"md-note\" data-note=\"说明\" title=\"说明\" tabindex=\"0\"><a href=\"https://example.com\">链接</a></span></p>\n",
                "链接",
            ),
            (
                "[文字]{`}`}",
                "<p><span class=\"md-note\" data-note=\"`\" title=\"`\" tabindex=\"0\">文字</span>`}</p>\n",
                "文字`}",
            ),
        ] {
            let html = parser.render(source);
            assert_eq!(html, expected, "{source}");
            assert_eq!(crate::text::extract(&parser.parse(source)).unwrap(), text);
        }
    }

    #[test]
    fn preserves_links_code_and_incomplete_syntax() {
        let parser = build_text();
        for source in [
            "[链接](https://example.com)",
            "[引用][ref]\n\n[ref]: https://example.com",
            "![图片](image.png)",
            "`[文字]{说明}`",
            "```\n[文字]{说明}\n```",
            r"\[文字]{说明}",
            "[文字]{未闭合",
            "[文字] {说明}",
            "[文字]{}",
            "[文字]{   }",
            "[]{说明}",
            "[跨\n行]{说明}",
            "[文字]{跨\n行}",
        ] {
            let html = parser.render(source);
            assert!(!html.contains("md-note"), "{source}: {html}");
        }
        assert!(
            parser
                .render("[链接](https://example.com)")
                .contains("<a href=")
        );
        assert!(
            parser
                .render("[引用][ref]\n\n[ref]: https://example.com")
                .contains("<a href=")
        );
    }
}
