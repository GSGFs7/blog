use lol_html::errors::RewritingError;
use lol_html::html_content::{ContentType, Element};
use lol_html::{HandlerResult, RewriteStrSettings, element, rewrite_str};

use super::component::Component;
use crate::rewriter::escape_html;

pub(crate) fn rewrite_raw_html(html: &str) -> Result<String, RewritingError> {
    if !html.contains("directive") {
        return Ok(html.to_owned());
    }

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
    let props = escape_html(&component.props_json(attributes.iter().cloned()));
    for (name, _) in &attributes {
        element.remove_attribute(name);
    }
    element.set_attribute("data-solid-island", component.name())?;
    element.set_attribute("data-props", &props)?;

    // placehold
    if let Some(placeholder) = component.placeholder() {
        element.set_inner_content(placeholder, ContentType::Html);
    }
    Ok(())
}

pub(crate) fn inject_music_placeholder(
    html: &str,
    placeholder: &str,
) -> Result<String, RewritingError> {
    rewrite_str(
        html,
        RewriteStrSettings::new().append_element_content_handler(element!(
            "[data-solid-island=MusicTrack]",
            |element| {
                element.set_inner_content(placeholder, ContentType::Html);
                Ok(())
            }
        )),
    )
}
