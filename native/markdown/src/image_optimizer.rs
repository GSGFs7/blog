use std::collections::HashMap;
use std::sync::LazyLock;

use lol_html::errors::RewritingError;
use lol_html::html_content::{ContentType, Element};
use lol_html::{HandlerResult, RewriteStrSettings, element, rewrite_str};
use regex::Regex;

use crate::types::ImageMetadata;

static CHECKSUM: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[a-f0-9]{64}$").unwrap());
static CHECKSUM_FILENAME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^([a-f0-9]{64})\.[A-Za-z0-9]+$").unwrap());

pub(crate) fn rewrite(
    html: &str,
    images: &HashMap<String, ImageMetadata>,
    image_picture_source_prefixes: &[String],
) -> Result<String, RewritingError> {
    rewrite_str(
        html,
        RewriteStrSettings::new().append_element_content_handler(element!(
            "img[src]",
            move |element: &mut Element<'_, '_>| rewrite_image(
                element,
                images,
                image_picture_source_prefixes
            )
        )),
    )
}

fn rewrite_image(
    element: &mut Element<'_, '_>,
    images: &HashMap<String, ImageMetadata>,
    image_picture_source_prefixes: &[String],
) -> HandlerResult {
    let Some(original_src) = element.get_attribute("src") else {
        return Ok(());
    };
    let Some(checksum) = extract_checksum(&original_src) else {
        return Ok(());
    };
    let Some(image) = images.get(&checksum) else {
        return Ok(());
    };
    if original_src != checksum
        && original_src != image.src
        && !image_picture_source_prefixes
            .iter()
            .any(|prefix| !prefix.is_empty() && original_src.starts_with(prefix))
    {
        return Ok(());
    }

    element.set_attribute("src", &image.src)?;
    if element.get_attribute("loading").is_none() {
        element.set_attribute("loading", "lazy")?;
    }
    if element.get_attribute("decoding").is_none() {
        element.set_attribute("decoding", "async")?;
    }
    if let Some(width) = image.width
        && element.get_attribute("width").is_none()
    {
        element.set_attribute("width", &width.to_string())?;
    }
    if let Some(height) = image.height
        && element.get_attribute("height").is_none()
    {
        element.set_attribute("height", &height.to_string())?;
    }
    if let Some(placeholder) = image.placeholder.as_deref() {
        let style = format!(
            "{} background-image: url({placeholder}); background-size: cover;",
            element.get_attribute("style").unwrap_or_default()
        )
        .trim()
        .to_owned();
        element.set_attribute("style", &style)?;
        let class = format!(
            "{} image-placeholder",
            element.get_attribute("class").unwrap_or_default()
        )
        .trim()
        .to_owned();
        element.set_attribute("class", &class)?;
    }

    let mut sources = String::new();
    if let Some(src) = image.avif_src.as_deref() {
        sources.push_str(&format!(
            "<source srcset=\"{}\" type=\"image/avif\">",
            crate::rewriter::escape_html(src)
        ));
    }
    if let Some(src) = image.webp_src.as_deref() {
        sources.push_str(&format!(
            "<source srcset=\"{}\" type=\"image/webp\">",
            crate::rewriter::escape_html(src)
        ));
    }
    element.before(&format!("<picture>{sources}"), ContentType::Html);
    element.after("</picture>", ContentType::Html);
    Ok(())
}

pub(crate) fn extract_checksum(src: &str) -> Option<String> {
    if CHECKSUM.is_match(src) {
        return Some(src.to_owned());
    }

    let path = src.split(['?', '#']).next().unwrap_or(src);
    let filename = path.rsplit('/').next().unwrap_or(path);
    CHECKSUM_FILENAME
        .captures(filename)
        .and_then(|captures| captures.get(1))
        .map(|capture| capture.as_str().to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sanitizer::sanitize;

    fn metadata(src: &str) -> ImageMetadata {
        ImageMetadata {
            src: src.to_owned(),
            avif_src: Some("/media/image.avif".to_owned()),
            webp_src: Some("/media/image.webp".to_owned()),
            width: Some(640),
            height: Some(480),
            placeholder: Some("data:image/webp;base64,eA==".to_owned()),
        }
    }

    #[test]
    fn optimizes_valid_sources_and_rejects_forged_external_urls() {
        let checksum = "a".repeat(64);
        let current_src = format!("/media/{checksum}.jpg");
        let mut images = HashMap::new();
        images.insert(checksum.clone(), metadata(&current_src));

        let html = format!(
            "<img src=\"{checksum}\" alt=\"bare\">\
             <img src=\"{current_src}\" alt=\"current\">\
             <img src=\"https://old.example/{checksum}.jpg\" alt=\"legacy\">\
             <img src=\"https://evil.example/{checksum}.jpg\" alt=\"forged\">"
        );
        let rewritten = rewrite(&html, &images, &["https://old.example/".to_owned()]).unwrap();

        assert_eq!(rewritten.matches("<picture>").count(), 3);
        assert_eq!(rewritten.matches("type=\"image/avif\"").count(), 3);
        assert_eq!(rewritten.matches("type=\"image/webp\"").count(), 3);
        assert!(rewritten.contains(&format!(
            "<img src=\"https://evil.example/{checksum}.jpg\" alt=\"forged\">"
        )));
        assert_eq!(rewritten.matches("width=\"640\"").count(), 3);
        assert_eq!(rewritten.matches("height=\"480\"").count(), 3);
        assert_eq!(rewritten.matches("image-placeholder").count(), 3);
        assert!(sanitize(&rewritten).contains("data:image/webp;base64,eA=="));
    }

    #[test]
    fn preserves_existing_attributes_and_missing_derivatives() {
        let checksum = "c".repeat(64);
        let mut image = metadata("/media/image.jpg");
        image.avif_src = None;
        image.webp_src = None;
        image.placeholder = None;
        let images = HashMap::from([(checksum.clone(), image)]);
        let html = format!(
            "<img src=\"{checksum}\" loading=\"eager\" decoding=\"sync\" \
             width=\"10\" height=\"20\">"
        );

        let rewritten = rewrite(&html, &images, &[]).unwrap();

        assert_eq!(
            rewritten,
            "<picture><img src=\"/media/image.jpg\" loading=\"eager\" \
             decoding=\"sync\" width=\"10\" height=\"20\"></picture>"
                .replace("             ", "")
        );
        assert!(!rewritten.contains("<source"));
    }
}
