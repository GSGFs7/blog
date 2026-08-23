use std::borrow::Cow;
use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use ammonia::Builder;
use regex::Regex;

const EXTRA_TAGS: &[&str] = &[
    "annotation",
    "maction",
    "math",
    "menclose",
    "merror",
    "mfrac",
    "mi",
    "mmultiscripts",
    "mn",
    "mo",
    "mover",
    "mpadded",
    "mphantom",
    "mprescripts",
    "mroot",
    "mrow",
    "ms",
    "mspace",
    "msqrt",
    "mstyle",
    "msub",
    "msubsup",
    "msup",
    "mtable",
    "mtd",
    "mtext",
    "mtr",
    "munder",
    "munderover",
    "none",
    "picture",
    "section",
    "semantics",
    "source",
    "input",
];
const GENERIC_ATTRIBUTES: &[&str] = &["aria-hidden", "class", "id", "title"];
const STYLE_PROPERTIES: &[&str] = &[
    "background-image",
    "background-size",
    "height",
    "left",
    "margin-left",
    "margin-right",
    "min-width",
    "right",
    "top",
    "vertical-align",
    "width",
    "--terminal-prompt",
];
const URL_SCHEMES: &[&str] = &["http", "https", "mailto", "tel"];

static CSS_DATA_URL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"(?i)url\(\s*['"]?(?P<url>data:[^'"\s)]+)"#).unwrap());
static SAFE_IMAGE_DATA_URL: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^data:image/(?:avif|gif|jpe?g|png|webp);base64,[A-Za-z0-9+/=]+$").unwrap()
});
static TERMINAL_PROMPT_STYLE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"^--terminal-prompt:"[\w@:/~.+#>$%?❯-]{1,16} "$"#).unwrap());
static SANITIZER: LazyLock<Builder<'static>> = LazyLock::new(build_sanitizer);

pub(crate) fn sanitize(html: &str) -> String {
    SANITIZER.clean(html).to_string()
}

fn build_sanitizer() -> Builder<'static> {
    let mut builder = Builder::default();
    builder
        .add_tags(EXTRA_TAGS)
        .add_generic_attributes(GENERIC_ATTRIBUTES)
        .add_tag_attributes("a", &["href", "target"])
        .add_tag_attributes("annotation", &["encoding"])
        .add_tag_attributes("code", &["class"])
        .add_tag_attributes("img", &["decoding", "loading", "style", "title"])
        .add_tag_attributes("input", &["checked", "disabled"])
        .add_tag_attributes("math", &["display", "xmlns"])
        .add_tag_attributes("pre", &["data-language"])
        .add_tag_attributes("source", &["media", "sizes", "srcset", "type"])
        .add_tag_attributes(
            "span",
            &[
                "data-caption",
                "data-domain",
                "style",
                "data-solid-island",
                "data-props",
            ],
        )
        .add_tag_attributes(
            "div",
            &[
                "data-solid-island",
                "data-props",
                "aria-label",
                "data-shell",
                "style",
            ],
        )
        .add_tag_attributes("td", &["colspan", "rowspan"])
        .add_tag_attributes("th", &["colspan", "rowspan"])
        .add_tag_attributes("time", &["datetime"])
        .clean_content_tags(HashSet::from(["script", "style"]))
        .tag_attribute_values(HashMap::from([
            (
                "input",
                HashMap::from([("type", HashSet::from(["checkbox"]))]),
            ),
            ("div", HashMap::from([("role", HashSet::from(["group"]))])),
        ]))
        .set_tag_attribute_values(HashMap::from([(
            "input",
            HashMap::from([("disabled", "")]),
        )]))
        .filter_style_properties(STYLE_PROPERTIES.iter().copied().collect())
        .url_schemes(URL_SCHEMES.iter().copied().collect())
        .attribute_filter(filter_attribute);
    builder
}

fn filter_attribute<'a>(tag: &str, attribute: &str, value: &'a str) -> Option<Cow<'a, str>> {
    if attribute == "style"
        && CSS_DATA_URL
            .captures_iter(value)
            .any(|captures| !SAFE_IMAGE_DATA_URL.is_match(&captures["url"]))
    {
        return None;
    }
    if tag == "div" && attribute == "style" && !TERMINAL_PROMPT_STYLE.is_match(value) {
        return None;
    }
    Some(Cow::Borrowed(value))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::html_fixtures;

    #[test]
    fn matches_frozen_nh3_fixtures() {
        for fixture in html_fixtures(include_str!("../tests/fixtures/sanitizer.json")) {
            assert_eq!(
                sanitize(&fixture.input),
                fixture.expected,
                "fixture: {}",
                fixture.name
            );
        }
    }
}
