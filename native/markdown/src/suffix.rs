use std::collections::HashMap;

use lol_html::errors::RewritingError;

use crate::types::ImageMetadata;
use crate::{
    code_language,
    domain_wrapper,
    image_optimizer,
    image_wrapper,
    sanitizer,
    solid_island,
    terminal,
};

// TODO: migrate to MarkdownIt plugins
pub(crate) fn rewrite(
    html: &str,
    images: &HashMap<String, ImageMetadata>,
    image_picture_source_prefixes: &[String],
) -> Result<String, RewritingError> {
    let html = domain_wrapper::rewrite(html)?;
    let html = image_optimizer::rewrite(&html, images, image_picture_source_prefixes)?;
    let html = image_wrapper::rewrite(&html)?;
    let html = code_language::rewrite(&html)?;
    let html = terminal::rewrite(&html)?;
    let html = solid_island::rewrite(&html)?;
    Ok(sanitizer::sanitize(&html))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runs_the_continuous_native_suffix_in_protocol_order() {
        let checksum = "a".repeat(64);
        let images = HashMap::from([(
            checksum.clone(),
            ImageMetadata {
                src: "/media/image.jpg".to_owned(),
                avif_src: None,
                webp_src: Some("/media/image.webp".to_owned()),
                width: Some(640),
                height: Some(480),
                placeholder: None,
            },
        )]);
        let html = format!(
            "<div class=\"directive terminal\"><pre><code class=\"language-command\">run</code></pre>\
             <img src=\"{checksum}\" alt=\"Shot\" onerror=\"alert(1)\"></div>"
        );

        let rewritten = rewrite(&html, &images, &[]).unwrap();

        assert!(rewritten.contains("class=\"terminal\""));
        assert!(rewritten.contains("data-language=\"command\""));
        assert!(rewritten.contains("class=\"md-img-container\" data-caption=\"Shot\""));
        assert!(rewritten.contains("<picture><source srcset=\"/media/image.webp\""));
        assert!(!rewritten.contains("directive"));
        assert!(!rewritten.contains("onerror"));
    }
}
