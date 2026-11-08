use std::sync::LazyLock;

use markdown_it::plugins::directives::{DirectiveKind, DirectiveNode, DirectiveRenderer};
use regex::Regex;

pub(crate) fn render_terminal(
    _kind: DirectiveKind,
    _name: &str,
    attributes: &[(String, String)],
    node: DirectiveNode<'_>,
    fmt: &mut DirectiveRenderer<'_, '_>,
) {
    let attribute = |name: &str| {
        attributes
            .iter()
            .find(|(attribute, _)| attribute.eq_ignore_ascii_case(name))
            .map(|(_, value)| value.as_str())
    };
    let shell = {
        static VALID: LazyLock<Regex> =
            LazyLock::new(|| Regex::new(r"^[a-z0-9][a-z0-9_+-]{0,31}$").unwrap());
        let value = attribute("shell").unwrap_or("bash").trim().to_lowercase();
        if VALID.is_match(&value) {
            value
        } else {
            "bash".to_owned()
        }
    };
    let prompt = {
        static VALID: LazyLock<Regex> =
            LazyLock::new(|| Regex::new(r"^[\w@:/~.+#>$%?❯-]{1,16}$").unwrap());
        let default = match shell.as_str() {
            "fish" => ">",
            "powershell" | "pwsh" => "PS>",
            "python" => ">>>",
            _ => "$",
        };
        let value = attribute("prompt").unwrap_or(default).trim();
        if VALID.is_match(value) {
            value.to_owned()
        } else {
            default.to_owned()
        }
    };
    let title = {
        static LINE_BREAK: LazyLock<Regex> = LazyLock::new(|| {
            Regex::new(r"\r\n|[\n\r\u{000B}\u{000C}\u{001C}-\u{001E}\u{0085}\u{2028}\u{2029}]")
                .unwrap()
        });
        let value = LINE_BREAK
            .split(attribute("title").unwrap_or("Terminal"))
            .collect::<Vec<_>>()
            .join(" ");
        let value = value.trim().chars().take(100).collect::<String>();
        if value.is_empty() {
            "Terminal".to_owned()
        } else {
            value
        }
    };

    fmt.cr();
    fmt.open(
        "div",
        &[
            ("class".into(), "terminal".into()),
            ("data-shell".into(), shell),
            ("role".into(), "group".into()),
            ("aria-label".into(), title.clone()),
            ("style".into(), format!(r#"--terminal-prompt:"{prompt} ""#)),
        ],
    );
    fmt.open(
        "div",
        &[
            ("class".into(), "terminal-title".into()),
            ("aria-hidden".into(), "true".into()),
        ],
    );
    fmt.text(&title);
    fmt.close("div");
    fmt.contents(node.children());
    fmt.close("div");
    fmt.cr();
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use crate::sanitizer::sanitize;

    #[test]
    fn renders_block_directives_without_html_rewriting() {
        let parser = crate::builder::build();
        for source in [
            "::terminal",
            ":::terminal\nhello\n:::",
            "::::terminal\n:::terminal\nhello\n:::\n::::",
        ] {
            let html = parser.render(source);
            assert!(html.contains("class=\"terminal\""), "{html}");
            assert!(html.contains("class=\"terminal-title\""), "{html}");
            assert!(!html.contains("directive terminal"), "{html}");
        }
    }

    #[test]
    fn renders_normalized_metadata() {
        for (source, shell, prompt, title) in [
            ("::terminal", "bash", "$", "Terminal"),
            ("::terminal{shell=python}", "python", ">>>", "Terminal"),
            ("::terminal{shell=pwsh}", "pwsh", "PS>", "Terminal"),
            ("::terminal{shell=fish}", "fish", ">", "Terminal"),
            (
                "::terminal{shell=\" ZSH \" prompt=\" ❯ \" title=数据库迁移}",
                "zsh",
                "❯",
                "数据库迁移",
            ),
            (
                "::terminal{SHELL=python TITLE=Uppercase PROMPT=❯}",
                "python",
                "❯",
                "Uppercase",
            ),
            (
                "::terminal{shell=python shell=bash title=first title=second}",
                "python",
                ">>>",
                "first",
            ),
            (
                "::terminal{shell=\"invalid shell\" prompt=\"x; color:red\" title=\"   \"}",
                "bash",
                "$",
                "Terminal",
            ),
            (
                "::terminal{title=\"A &amp; B &#10; second\" prompt=\"&gt;\"}",
                "bash",
                "$",
                "A &amp; B &#10; second",
            ),
        ] {
            let title = crate::rewriter::escape_html(title);
            let prompt = crate::rewriter::escape_html(prompt);
            assert_eq!(
                crate::builder::build().render(source),
                format!(
                    "<div class=\"terminal\" data-shell=\"{shell}\" role=\"group\" aria-label=\"{title}\" style=\"--terminal-prompt:&quot;{prompt} &quot;\"><div class=\"terminal-title\" aria-hidden=\"true\">{title}</div></div>\n"
                ),
                "source: {source}",
            );
        }
    }

    #[test]
    fn preserves_nested_content_through_the_pipeline() {
        let html = crate::builder::build().render(
            "::::terminal{title=outer}\n:::terminal{title=inner}\n```command\necho hello\n```\n\n[link](https://example.com)\n\n![caption](image.png)\n\n::counter{initial=2}\n:::\n::::",
        );
        let html = crate::suffix::rewrite(&html, &HashMap::new(), &[], None).unwrap();
        assert_eq!(html.matches("class=\"terminal\"").count(), 2);
        assert!(html.contains("data-language=\"command\""));
        assert!(html.contains("echo hello"));
        assert!(html.contains("data-domain=\"example.com\""));
        assert!(html.contains("data-caption=\"caption\""));
        assert!(html.contains("data-solid-island=\"Counter\""));
    }

    #[test]
    fn leaves_raw_html_and_inline_directives_unconverted() {
        for source in [
            "<div class=\"directive terminal\" shell=\"python\" onclick=\"bad()\">raw</div>",
            "before :terminal{title=inline} after",
        ] {
            let html = crate::builder::build().render(source);
            let html = crate::suffix::rewrite(&html, &HashMap::new(), &[], None).unwrap();
            assert!(html.contains("class=\"directive terminal\""));
            assert!(!html.contains("terminal-title"));
            assert!(!html.contains("data-shell"));
            assert!(!html.contains("onclick"));
        }
    }

    #[test]
    fn sanitizes_native_terminal_content_and_metadata() {
        let html = crate::builder::build().render(
            ":::terminal{title=\"<script>bad()</script>\" shell=\"bash;bad\" prompt=\"x; color:red\" onclick=bad}\n<script>bad()</script>\n:::",
        );
        let cleaned = sanitize(&html);
        assert!(cleaned.contains("&lt;script&gt;bad()&lt;/script&gt;"));
        assert!(cleaned.contains("data-shell=\"bash\""));
        assert!(cleaned.contains("--terminal-prompt:&quot;$ &quot;"));
        assert!(!cleaned.contains("<script>"));
        assert!(!cleaned.contains("onclick"));
        assert!(!cleaned.contains("color:red"));
    }

    #[test]
    fn truncates_title_to_one_hundred_unicode_characters() {
        let html = crate::builder::build()
            .render(&format!("::terminal{{title=\"{}\"}}", "界".repeat(101),));

        assert!(html.contains(&format!("aria-label=\"{}\"", "界".repeat(100))));
        assert!(!html.contains(&"界".repeat(101)));
    }
}
