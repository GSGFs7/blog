use std::cell::RefCell;
use std::collections::HashSet;

use html5ever::tendril::StrTendril;
use html5ever::tokenizer::{
    BufferQueue, TagKind, Token, TokenSink, TokenSinkResult, Tokenizer, TokenizerOpts,
};
use lol_html::{RewriteStrSettings, element, html_content::ContentType, rewrite_str};
use markdown_it::document::{Document, Node, StructuralEvent, Text, TextSpecial};
use markdown_it::plugins::cmark::block::blockquote::Blockquote;
use markdown_it::plugins::cmark::block::heading::ATXHeading;
use markdown_it::plugins::cmark::block::hr::ThematicBreak;
use markdown_it::plugins::cmark::block::lheading::SetextHeader;
use markdown_it::plugins::cmark::block::list::ListItem;
use markdown_it::plugins::cmark::block::paragraph::Paragraph;
use markdown_it::plugins::cmark::inline::image::Image;
use markdown_it::plugins::cmark::inline::newline::{Hardbreak, Softbreak};
use markdown_it::plugins::directives::{ContainerDirective, LeafDirective};
use markdown_it::plugins::extra::tables::{TableCell, TableRow};
use markdown_it::plugins::html::html_block::HtmlBlock;
use markdown_it::plugins::html::html_inline::HtmlInline;

pub(crate) fn extract(document: &Document) -> Result<String, lol_html::errors::RewritingError> {
    let mut text = String::new();
    let mut ignored = None;
    let mut suppressed = None;

    for event in document.events(document.root()) {
        let node = event.node();
        if let Some(id) = ignored {
            if matches!(event, StructuralEvent::Exit(_)) && node.id() == id {
                ignored = None;
            }
            continue;
        }

        if is_ignored(node) {
            if matches!(event, StructuralEvent::Enter(_)) {
                ignored = Some(node.id());
            }
            continue;
        }

        if let Some(raw) = node.cast::<HtmlInline>() {
            if matches!(event, StructuralEvent::Leaf(_) | StructuralEvent::Enter(_)) {
                apply_inline_html(&raw.content, &mut suppressed, &mut text);
            }
            continue;
        }

        if matches!(event, StructuralEvent::Exit(_)) {
            if is_block(node) || node.is::<TableCell>() {
                suppressed = None;
            }
            if node.is::<TableCell>() {
                text.push('\t');
            }
            continue;
        }

        if suppressed.is_some() {
            continue;
        }

        if is_block(node) {
            newline(&mut text);
        }

        if let Some(value) = node.cast::<Text>() {
            text.push_str(&value.content);
        } else if let Some(value) = node.cast::<TextSpecial>() {
            text.push_str(&value.content);
        } else if let Some(raw) = node.cast::<HtmlBlock>() {
            newline(&mut text);
            text.push_str(&html_to_text(&raw.content)?);
            newline(&mut text);
        } else if node.is::<Softbreak>() || node.is::<Hardbreak>() {
            newline(&mut text);
        }
    }

    Ok(text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join("\n"))
}

#[derive(Default)]
struct InlineHtmlSink {
    events: RefCell<Vec<(bool, String)>>,
}

impl TokenSink for InlineHtmlSink {
    type Handle = ();

    fn process_token(&self, token: Token, _: u64) -> TokenSinkResult<Self::Handle> {
        if let Token::TagToken(tag) = token {
            self.events.borrow_mut().push((
                tag.kind == TagKind::EndTag,
                tag.name.to_string().to_ascii_lowercase(),
            ));
        }
        TokenSinkResult::Continue
    }
}

fn inline_tags(raw: &str) -> Vec<(bool, String)> {
    let tokenizer = Tokenizer::new(InlineHtmlSink::default(), TokenizerOpts::default());
    let queue = BufferQueue::default();
    queue.push_back(StrTendril::from(raw));
    let _ = tokenizer.feed(&queue);
    tokenizer.end();
    tokenizer.sink.events.into_inner()
}

fn apply_inline_html(raw: &str, suppressed: &mut Option<String>, text: &mut String) {
    for (is_end, name) in inline_tags(raw) {
        if is_suppressing_tag(&name) {
            if is_end {
                if suppressed.as_deref() == Some(name.as_str()) {
                    *suppressed = None;
                }
            } else if suppressed.is_none() {
                *suppressed = Some(name);
            }
        } else if suppressed.is_none() && is_block_tag(&name) {
            newline(text);
        }
    }
}

fn is_suppressing_tag(name: &str) -> bool {
    matches!(name, "script" | "style" | "pre")
}

fn is_block_tag(name: &str) -> bool {
    matches!(
        name,
        "address"
            | "article"
            | "aside"
            | "blockquote"
            | "br"
            | "dd"
            | "div"
            | "dl"
            | "dt"
            | "footer"
            | "h1"
            | "h2"
            | "h3"
            | "h4"
            | "h5"
            | "h6"
            | "header"
            | "hr"
            | "li"
            | "main"
            | "nav"
            | "ol"
            | "p"
            | "section"
            | "table"
            | "tr"
            | "ul"
    )
}

fn html_to_text(html: &str) -> Result<String, lol_html::errors::RewritingError> {
    let spaced = rewrite_str(
        html,
        RewriteStrSettings::new()
            .append_element_content_handler(element!(
                "address, article, aside, blockquote, br, dd, div, dl, dt, footer, h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, section, table, tr, ul",
                |element| {
                    element.before("\n", ContentType::Text);
                    element.after("\n", ContentType::Text);
                    Ok(())
                }
            ))
            .append_element_content_handler(element!("td, th", |element| {
                element.after("\t", ContentType::Text);
                Ok(())
            })),
    )?;
    let cleaned = ammonia::Builder::default()
        .tags(HashSet::new())
        .clean_content_tags(HashSet::from(["script", "style", "pre"]))
        .clean(&spaced)
        .to_string();
    Ok(html_escape::decode_html_entities(&cleaned).into_owned())
}

fn newline(output: &mut String) {
    if !output.is_empty() && !output.ends_with('\n') {
        output.push('\n');
    }
}

fn is_block(node: &Node) -> bool {
    node.is::<Paragraph>()
        || node.is::<ATXHeading>()
        || node.is::<SetextHeader>()
        || node.is::<ListItem>()
        || node.is::<Blockquote>()
        || node.is::<ThematicBreak>()
        || node.is::<TableRow>()
        || node.is::<ContainerDirective>()
        || node.is::<LeafDirective>()
}

fn is_ignored(node: &Node) -> bool {
    node.is::<Image>()
}

#[cfg(test)]
mod tests {
    use crate::builder::build_text;

    #[test]
    fn strips_markdown_and_keeps_text_structure() {
        let parser = build_text();
        for (source, expected) in [
            ("", ""),
            (
                "# 标题\n\n**粗体 *斜体***、~~删除~~、==高亮==",
                "标题\n粗体 斜体、删除、高亮",
            ),
            (
                "标题\n====\n\n> 引用\n\n- [x] 完成\n- 未完成",
                "标题\n引用\n完成\n未完成",
            ),
            ("[**链接**][ref]\n\n[ref]: https://example.com", "链接"),
            ("![**图片**](image.png)\n\n![图片][img]\n\n[img]: /x", ""),
            ("---\ntitle: 标题\n---\n正文", "正文"),
            ("+++\ntitle = '标题'\n+++\n正文", "正文"),
            (
                "前文\n\n```rust\nfn main() {}\n```\n\n    code\n\n后文 `a < b`",
                "前文\n后文 a < b",
            ),
            ("前 $x^2$ 后\n\n$$\nx + y\n$$\n\n正文", "前  后\n正文"),
            (r"\*原样\* &amp; &lt;b&gt; `&amp;`", "*原样* & <b> &amp;"),
            ("| A | B |\n|---|---|\n| 一 | 二 |", "A\tB\n一\t二"),
            (":::spoiler{title=隐藏}\n内部 **正文**\n:::", "内部 正文"),
            (
                "<p>一<strong>二</strong></p><p>三<br>四</p>",
                "一二\n三\n四",
            ),
            ("前<div>中</div>后", "前\n中\n后"),
            (
                r#"正文 <span title="<script>">可见</span> 后文"#,
                "正文 可见 后文",
            ),
            ("前文 <script>\n\n</script>\n\n后文", "前文\n后文"),
            ("前 <script>alert(1)\n\n后文", "前\n后文"),
            ("<table><tr><td>甲</td><td>乙</td></tr></table>", "甲\t乙"),
            (
                "<table><tr><th>甲</th><th>乙</th></tr><tr><td>丙</td><td>丁</td></tr></table>",
                "甲\t乙\n丙\t丁",
            ),
            (
                "正文 <script>bad()</script><style>.bad{}</style><!-- 隐藏 --> 后文",
                "正文  后文",
            ),
            (
                "<div>正文 &amp; 文本<pre>代码</pre><img src='/x'></div>",
                "正文 & 文本",
            ),
        ] {
            assert_eq!(
                super::extract(&parser.parse(source)).unwrap(),
                expected,
                "{source}"
            );
        }
    }
}
