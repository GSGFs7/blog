use lol_html::errors::RewritingError;
use lol_html::html_content::Element;
use lol_html::{HandlerResult, RewriteStrSettings, element, rewrite_str};

use crate::rewriter::escape_html;

enum Component {
    Counter,
    PythonRepl,
    Chart,
}

impl Component {
    fn from_directive(name: &str) -> Option<Self> {
        match name {
            "counter" => Some(Self::Counter),
            "python-wasm" | "python-repl" => Some(Self::PythonRepl),
            "chart" | "charts" => Some(Self::Chart),
            _ => None,
        }
    }

    fn name(&self) -> &'static str {
        match self {
            Self::Counter => "Counter",
            Self::PythonRepl => "PythonREPL",
            Self::Chart => "Chart",
        }
    }

    fn allows_prop(&self, name: &str) -> bool {
        match self {
            Self::Counter => name == "initial",
            Self::PythonRepl => false,
            Self::Chart => matches!(name, "formula" | "x-min" | "x-max" | "y-min" | "y-max"),
        }
    }
}

pub(crate) fn rewrite(html: &str) -> Result<String, RewritingError> {
    rewrite_str(
        html,
        RewriteStrSettings::new()
            .append_element_content_handler(element!("span, div", rewrite_element)),
    )
}

fn rewrite_element(element: &mut Element<'_, '_>) -> HandlerResult {
    let Some(classes) = element.get_attribute("class") else {
        return Ok(());
    };
    let classes: Vec<_> = classes.split_whitespace().collect();
    if !classes.contains(&"directive") {
        return Ok(());
    }
    let Some(component) = classes
        .iter()
        .find(|name| **name != "directive")
        .and_then(|name| Component::from_directive(name))
    else {
        return Ok(());
    };

    let attributes: Vec<_> = element
        .attributes()
        .iter()
        .map(|attribute| (attribute.name(), attribute.value()))
        .collect();
    let props = attributes
        .iter()
        .filter(|(name, _)| component.allows_prop(name))
        .map(|(name, value)| (name.as_str(), value.as_str()));
    let props = escape_html(&serialize_props(props));

    for (name, _) in &attributes {
        element.remove_attribute(name);
    }
    element.set_attribute("data-solid-island", component.name())?;
    element.set_attribute("data-props", &props)?;
    Ok(())
}

fn serialize_props<'a>(props: impl Iterator<Item = (&'a str, &'a str)>) -> String {
    let props = props
        .map(|(name, value)| {
            format!(
                "{}:{}",
                serde_json::to_string(name).expect("string serialization cannot fail"),
                serde_json::to_string(value).expect("string serialization cannot fail")
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!("{{{props}}}")
}

#[cfg(test)]
mod tests {
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
    fn matches_frozen_python_fixtures() {
        let fixtures: Vec<SolidIslandFixture> =
            fixtures(include_str!("../tests/fixtures/solid_island.json"));
        for fixture in fixtures {
            let rewritten = rewrite(&fixture.input).unwrap();
            assert_eq!(rewritten, fixture.rewritten, "fixture: {}", fixture.name);
            assert_eq!(
                sanitize(&rewritten),
                fixture.sanitized,
                "sanitized fixture: {}",
                fixture.name
            );
        }
    }
}
