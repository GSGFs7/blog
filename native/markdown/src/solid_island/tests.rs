use markdown_it::MarkdownIt;
use markdown_it::plugins::directives;
use serde::Deserialize;

use super::*;
use crate::sanitizer::sanitize;
use crate::test_support::fixtures;

#[derive(Deserialize)]
struct SolidIslandFixture {
    name: String,
    input: String,
    rewritten: String,
    sanitized: String,
}

#[test]
fn native_directives_match_legacy_html_conversion() {
    let parser = crate::builder::build();
    let mut legacy = MarkdownIt::empty();
    markdown_it::plugins::cmark::add(&mut legacy);
    directives::add(&mut legacy);
    markdown_it::plugins::html::add(&mut legacy);

    for name in [
        "counter",
        "python-wasm",
        "python-repl",
        "python-playground",
        "chart",
        "charts",
        "music",
        "model",
    ] {
        for attrs in [
            "",
            r#"{initial=2 source=code title=chart formula=x src="https://example.com/a?x=1&y=2" alt=model x-min=-1 x-max=2 y-min=-3 y-max=4 hide-input=true disable-drag=true ignored=bad onclick=bad}"#,
            r#"{INITIAL=first initial=second TITLE="A & B < > ' &quot;" SRC="a?x=1&amp;y=2" FORMULA="x < 2"}"#,
        ] {
            for source in [
                format!("before :{name}{attrs} after"),
                format!("::{name}{attrs}"),
                format!(":::{name}{attrs}\n**content**\n:::"),
                format!("::::{name}{attrs}\n:::counter{{initial=3}}\ninner\n:::\n::::"),
            ] {
                let expected = rewrite_raw_html(&legacy.render(&source)).unwrap();
                let actual = parser.render(&source);
                assert_eq!(actual, expected, "source: {source}");
                assert!(!actual.contains("class=\"directive"), "{actual}");
                assert_eq!(rewrite_raw_html(&actual).unwrap(), actual);
                assert_eq!(sanitize(&actual), sanitize(&expected));
            }
        }
    }
}

#[test]
fn unknown_directives_keep_default_rendering() {
    assert_eq!(
        crate::builder::build().render("::unknown{initial=2}"),
        "<div class=\"directive unknown\" initial=\"2\"></div>\n"
    );
}

#[test]
fn music_directive_preserves_only_src_through_sanitization() {
    let rendered = crate::builder::build()
        .render(r#"::music{src="https://example.com/a.mp3?x=1&y=2" url="ignored" onclick="bad"}"#);
    let cleaned = sanitize(&rendered);
    assert!(cleaned.contains("data-solid-island=\"MusicTrack\""));
    assert!(cleaned.contains("https://example.com/a.mp3?x=1&amp;y=2"));
    assert!(!cleaned.contains("ignored"));
    assert!(!cleaned.contains("onclick"));
    assert!(!cleaned.contains("data-solid-ssr"));
}

#[test]
fn music_placeholder_replaces_directive_content() {
    for tag in ["span", "div"] {
        let html =
            format!("<{tag} class=\"directive music\" src=\"song.mp3\"><b>ignored</b></{tag}>");
        let cleaned = sanitize(&rewrite_raw_html(&html).unwrap());
        assert!(!cleaned.contains("ignored"));
    }
}

#[test]
fn model_placeholder_survives_sanitization() {
    let rendered = crate::builder::build()
        .render(r#"::model{src="https://example.com/model.glb" alt="3D model" onclick="bad"}"#);
    let cleaned = sanitize(&rendered);
    assert!(cleaned.contains("data-solid-island=\"ModelViewer\""));
    assert!(
        cleaned
            .contains(r#"<span class="model-viewer-status">Scroll here to load the model</span>"#)
    );
    assert!(cleaned.contains("https://example.com/model.glb"));
    assert!(!cleaned.contains("onclick"));
    assert!(!cleaned.contains("data-solid-ssr"));
}

#[test]
fn matches_frozen_python_fixtures() {
    let fixtures: Vec<SolidIslandFixture> =
        fixtures(include_str!("../../tests/fixtures/solid_island.json"));
    for fixture in fixtures {
        let rewritten = rewrite_raw_html(&fixture.input).unwrap();
        assert_eq!(rewritten, fixture.rewritten, "fixture: {}", fixture.name);
        assert_eq!(
            sanitize(&rewritten),
            fixture.sanitized,
            "sanitized fixture: {}",
            fixture.name
        );
    }
}
