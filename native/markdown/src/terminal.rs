use std::sync::LazyLock;

use html_escape::decode_html_entities;
use lol_html::errors::RewritingError;
use lol_html::html_content::{ContentType, Element};
use lol_html::{HandlerResult, RewriteStrSettings, element, rewrite_str};
use regex::Regex;

use crate::rewriter::escape_html;

static SHELL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[a-z0-9][a-z0-9_+-]{0,31}$").unwrap());
static PROMPT: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[\w@:/~.+#>$%?❯-]{1,16}$").unwrap());
static TITLE_LINE_BREAK: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\r\n|[\n\r\u{000B}\u{000C}\u{001C}-\u{001E}\u{0085}\u{2028}\u{2029}]").unwrap()
});

pub(crate) fn rewrite(html: &str) -> Result<String, RewritingError> {
    rewrite_str(
        html,
        RewriteStrSettings::new().append_element_content_handler(element!("div", rewrite_element)),
    )
}

fn rewrite_element(element: &mut Element<'_, '_>) -> HandlerResult {
    let Some(classes) = element.get_attribute("class") else {
        return Ok(());
    };
    let classes: Vec<_> = classes.split_whitespace().collect();
    if !classes.contains(&"directive") || !classes.contains(&"terminal") {
        return Ok(());
    }

    let attributes: Vec<_> = element
        .attributes()
        .iter()
        .map(|attribute| (attribute.name(), attribute.value()))
        .collect();
    let shell = normalize_shell(attribute(&attributes, "shell").unwrap_or("bash"));
    let default_prompt = default_prompt(&shell);
    let prompt = normalize_prompt(
        attribute(&attributes, "prompt").unwrap_or(default_prompt),
        default_prompt,
    );
    let title = normalize_title(attribute(&attributes, "title").unwrap_or("Terminal"));
    let title = if title.is_empty() {
        "Terminal".to_owned()
    } else {
        title
    };

    for (name, _) in &attributes {
        element.remove_attribute(name);
    }
    element.set_attribute("class", "terminal")?;
    element.set_attribute("data-shell", &shell)?;
    element.set_attribute("role", "group")?;
    element.set_attribute("aria-label", &escape_html(&title))?;
    element.set_attribute(
        "style",
        &escape_html(&format!(r#"--terminal-prompt:"{prompt} ""#)),
    )?;
    element.prepend(
        &format!(
            r#"<div class="terminal-title" aria-hidden="true">{}</div>"#,
            escape_html(&title)
        ),
        ContentType::Html,
    );
    Ok(())
}

fn attribute<'a>(attributes: &'a [(String, String)], name: &str) -> Option<&'a str> {
    attributes
        .iter()
        .find(|(attribute, _)| attribute == name)
        .map(|(_, value)| value.as_str())
}

fn normalize_shell(value: &str) -> String {
    let value = decode_html_entities(value).trim().to_lowercase();
    if SHELL.is_match(&value) {
        value
    } else {
        "bash".to_owned()
    }
}

fn normalize_prompt(value: &str, default: &str) -> String {
    let value = decode_html_entities(value).trim().to_owned();
    if PROMPT.is_match(&value) {
        value
    } else {
        default.to_owned()
    }
}

fn normalize_title(value: &str) -> String {
    let value = decode_html_entities(value);
    let value = TITLE_LINE_BREAK.split(&value).collect::<Vec<_>>().join(" ");
    value.trim().chars().take(100).collect()
}

fn default_prompt(shell: &str) -> &'static str {
    match shell {
        "bash" | "sh" | "zsh" => "$",
        "fish" => ">",
        "powershell" | "pwsh" => "PS>",
        "python" => ">>>",
        _ => "$",
    }
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    use super::*;
    use crate::sanitizer::sanitize;
    use crate::solid_island;
    use crate::test_support::fixtures;

    #[derive(Deserialize)]
    struct TerminalFixture {
        name: String,
        input: String,
        terminal: String,
        solid: String,
        sanitized: String,
    }

    #[test]
    fn matches_frozen_python_fixtures() {
        let fixtures: Vec<TerminalFixture> =
            fixtures(include_str!("../tests/fixtures/terminal.json"));
        for fixture in fixtures {
            let terminal = rewrite(&fixture.input).unwrap();
            assert_eq!(terminal, fixture.terminal, "fixture: {}", fixture.name);
            let solid = solid_island::rewrite(&terminal).unwrap();
            assert_eq!(solid, fixture.solid, "solid fixture: {}", fixture.name);
            assert_eq!(
                sanitize(&solid),
                fixture.sanitized,
                "sanitized fixture: {}",
                fixture.name
            );
        }
    }

    #[test]
    fn truncates_title_to_one_hundred_unicode_characters() {
        let title = normalize_title(&"界".repeat(101));

        assert_eq!(title.chars().count(), 100);
    }
}
