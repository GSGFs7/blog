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
    "svg",
    "path",
    "line",
];
const GENERIC_ATTRIBUTES: &[&str] = &["aria-hidden", "class", "id", "title"];
const STYLE_PROPERTIES: &[&str] = &[
    "background-image",
    "background-size",
    "background-color",
    "border",
    "border-bottom-width",
    "border-color",
    "border-right-style",
    "border-right-width",
    "border-top-width",
    "border-style",
    "border-width",
    "bottom",
    "color",
    "height",
    "left",
    "margin-left",
    "margin-right",
    "margin",
    "margin-top",
    "min-width",
    "padding-left",
    "right",
    "top",
    "text-align",
    "text-shadow",
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
        .add_tag_attributes(
            "svg",
            &["xmlns", "width", "height", "viewBox", "preserveAspectRatio"],
        )
        .add_tag_attributes("path", &["d"])
        .add_tag_attributes("line", &["x1", "x2", "y1", "y2", "stroke-width"])
        .add_tag_attributes("mfrac", &["linethickness"])
        .add_tag_attributes("mstyle", &["style"])
        .add_tag_attributes(
            "mo",
            &[
                "fence",
                "stretchy",
                "symmetric",
                "separator",
                "largeop",
                "movablelimits",
                "minsize",
                "maxsize",
                "lspace",
                "rspace",
            ],
        )
        .add_tag_attributes("mover", &["accent"])
        .add_tag_attributes("munder", &["accentunder"])
        .add_tag_attributes("munderover", &["accent", "accentunder"])
        .add_tag_attributes(
            "mpadded",
            &["width", "height", "depth", "lspace", "voffset", "style"],
        )
        .add_tag_attributes("mspace", &["width", "height", "depth", "linebreak"])
        .add_tag_attributes("menclose", &["notation", "style"])
        .add_tag_attributes(
            "mtable",
            &[
                "columnalign",
                "columnlines",
                "columnspacing",
                "rowlines",
                "rowspacing",
                "align",
                "width",
            ],
        )
        .add_tag_attributes("mtd", &["columnalign", "columnspan", "rowspan"])
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
        .add_tag_attributes("td", &["colspan", "rowspan", "style"])
        .add_tag_attributes("th", &["colspan", "rowspan", "style"])
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
    for tag in EXTRA_TAGS.iter().filter(|tag| tag.starts_with('m')) {
        builder.add_tag_attributes(
            tag,
            &[
                "mathcolor",
                "mathbackground",
                "mathvariant",
                "mathsize",
                "displaystyle",
                "scriptlevel",
            ],
        );
    }
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
    fn preserves_rendered_math_line_widths() {
        let parser = crate::builder::build();
        let line = Regex::new(r#"<span class="(?:frac-line|overline-line|underline-line)" style="border-bottom-width:[^";]+"#).unwrap();
        for expression in [r"\frac{x}{y}", r"\overline{x}", r"\underline{x}"] {
            for markdown in [format!("${expression}$"), format!("$$\n{expression}\n$$")] {
                let rendered = parser.parse(&markdown).render();
                let expected = line.find(&rendered).expect("rendered math line with width");
                assert!(
                    sanitize(&rendered).contains(expected.as_str()),
                    "{markdown}"
                );
            }
        }
    }

    #[test]
    fn preserves_math_graphics_and_presentation() {
        let parser = crate::builder::build();
        for (expression, expected) in [
            (
                r"\sqrt{x}",
                vec![
                    "<svg",
                    "<path d=",
                    "viewBox=",
                    "preserveAspectRatio=",
                    "padding-left:",
                ],
            ),
            (r"\widehat{abc}", vec!["<svg", "<path d="]),
            (r"\xrightarrow{abc}", vec!["<svg", "<path d=", "lspace="]),
            (
                r"\cancel{x}",
                vec!["<line", "stroke-width=", "notation=\"updiagonalstrike\""],
            ),
            (r"\boxed{x}", vec!["border-width:", "border-style:solid"]),
            (r"\color{red}{x}", vec!["color:red", "mathcolor=\"red\""]),
            (
                r"\colorbox{yellow}{x}",
                vec!["background-color:yellow", "mathbackground=\"yellow\""],
            ),
            (
                r"\fcolorbox{red}{yellow}{x}",
                vec!["border-color:red", "background-color:yellow", "border:"],
            ),
            (
                r"\rule[1ex]{2em}{0.4pt}",
                vec!["border-top-width:", "border-right-width:2em", "bottom:"],
            ),
            (r"\pmb{x}", vec!["text-shadow:"]),
            (r"\mathrm{x}", vec!["mathvariant=\"normal\""]),
            (
                r"a\\[1em]b",
                vec!["margin-top:1em", "linebreak=\"newline\""],
            ),
            (
                r"\binom{n}{k}",
                vec!["linethickness=\"0px\"", "fence=\"true\""],
            ),
            (
                r"\begin{array}{r|l}a&b\\\hline c&d\end{array}",
                vec!["columnalign=", "rowspacing=", "border-right-style:"],
            ),
        ] {
            for markdown in [format!("${expression}$"), format!("$$\n{expression}\n$$")] {
                let rendered = parser.parse(&markdown).render();
                let cleaned = sanitize(&rendered);
                for fragment in &expected {
                    assert!(
                        rendered.contains(fragment),
                        "renderer: {markdown}: {fragment}"
                    );
                    assert!(
                        cleaned.contains(fragment),
                        "sanitizer: {markdown}: {fragment}"
                    );
                }
            }
        }
    }

    #[test]
    fn preserves_table_alignment() {
        let rendered = crate::builder::build()
            .parse("| L | C | R |\n| :--- | :---: | ---: |\n| a | b | c |")
            .render();
        let cleaned = sanitize(&rendered);
        for tag in ["th", "td"] {
            for alignment in ["left", "center", "right"] {
                assert!(cleaned.contains(&format!("<{tag} style=\"text-align:{alignment}\">")));
            }
        }
    }

    #[test]
    fn rejects_active_svg_and_math_content() {
        let cleaned = sanitize(
            r#"<svg onload="alert(1)"><script>alert(2)</script><foreignObject><iframe src="https://example.com"></iframe></foreignObject><use href="https://example.com/x.svg#x"></use><animate attributeName="href" values="javascript:alert(3)"></animate><path d="M0 0L1 1" onclick="alert(4)" fill="url(https://example.com/x)"></path><line x1="0" y1="0" x2="1" y2="1" stroke-width="1" onmouseover="alert(5)"></line></svg><math href="javascript:alert(6)"><mi mathcolor="red" onclick="alert(7)">x</mi></math><span style="color:red;position:fixed;z-index:999">safe</span>"#,
        );
        for forbidden in [
            "onload",
            "onclick",
            "onmouseover",
            "<script",
            "<foreignObject",
            "<iframe",
            "<use",
            "<animate",
            "href=",
            "fill=",
            "alert(",
            "position:",
            "z-index:",
        ] {
            assert!(!cleaned.contains(forbidden), "{forbidden}: {cleaned}");
        }
        assert!(cleaned.contains("<path d=\"M0 0L1 1\""));
        assert!(cleaned.contains("mathcolor=\"red\""));
    }

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
