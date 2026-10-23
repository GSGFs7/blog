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
    music_placeholder: Option<&str>,
) -> Result<String, RewritingError> {
    let html = domain_wrapper::rewrite(html)?;
    let html = image_optimizer::rewrite(&html, images, image_picture_source_prefixes)?;
    let html = image_wrapper::rewrite(&html)?;
    let html = code_language::rewrite(&html)?;
    let html = terminal::rewrite(&html)?;
    let html = solid_island::rewrite(&html)?;
    let html = sanitizer::sanitize(&html);
    let html = image_optimizer::inject_placeholders(&html, images)?;
    match music_placeholder {
        Some(placeholder) => solid_island::inject_music_placeholder(&html, placeholder),
        None => Ok(html),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preserves_validated_image_placeholders_after_sanitizing_user_html() {
        let checksum = "a".repeat(64);
        let images = HashMap::from([(
            checksum.clone(),
            ImageMetadata {
                src: "/media/image.jpg?v=1&size=2".to_owned(),
                avif_src: None,
                webp_src: None,
                width: None,
                height: None,
                placeholder: Some("data:image/webp;base64,eA==".to_owned()),
            },
        )]);
        let html = format!(
            r#"<img src="{checksum}" class="custom" onerror="bad()" style="width:10px;position:fixed"><img src="https://evil.example/{checksum}.jpg" class="image-placeholder" style="background-image:url(data:image/webp;base64,AAAA)"><a href="data:text/html,boom">link</a>"#
        );

        let rewritten = rewrite(&html, &images, &[], None).unwrap();

        assert!(rewritten.contains("src=\"/media/image.jpg?v=1&amp;size=2\""));
        assert!(rewritten.contains("class=\"custom image-placeholder\""));
        assert!(rewritten.contains(
            "width:10px;background-image:url(data:image/webp;base64,eA==);background-size:cover"
        ));
        assert_eq!(rewritten.matches("data:image/").count(), 1);
        for forbidden in ["bad()", "position:", "data:text/html", "AAAA"] {
            assert!(!rewritten.contains(forbidden), "{rewritten}");
        }
    }

    #[test]
    fn rejects_invalid_placeholder_metadata() {
        let checksum = "a".repeat(64);
        for placeholder in [
            "data:text/html;base64,eA==",
            "data:image/svg+xml;base64,eA==",
            "https://evil.example/image.png",
            "data:image/webp;base64,eA==);position:fixed",
            "data:image/webp;base64,eA==\" onerror=\"bad()",
            "data:image/webp;base64,eA==\n",
            "data:image/webp;base64,",
            "data:image/webp;base64,eA===",
        ] {
            let images = HashMap::from([(
                checksum.clone(),
                ImageMetadata {
                    src: "/media/image.jpg".to_owned(),
                    avif_src: None,
                    webp_src: None,
                    width: None,
                    height: None,
                    placeholder: Some(placeholder.to_owned()),
                },
            )]);
            let rewritten = rewrite(
                &format!(r#"<img src="{checksum}" style="width:10px">"#),
                &images,
                &[],
                None,
            )
            .unwrap();

            assert!(rewritten.contains("src=\"/media/image.jpg\""));
            assert!(rewritten.contains("style=\"width:10px\""));
            assert!(!rewritten.contains("image-placeholder"), "{placeholder}");
            assert!(!rewritten.contains("background-image"), "{placeholder}");
        }
    }

    #[test]
    fn inserts_trusted_music_placeholder_after_sanitizing_user_html() {
        let placeholder = "<button disabled><svg><circle r=\"3\"></circle></svg></button>";
        let html = "<div class=\"directive music\" src=\"song.mp3\" onclick=\"bad()\">\
                    <script>bad()</script></div><script>bad()</script>";
        let rewritten = rewrite(html, &HashMap::new(), &[], Some(placeholder)).unwrap();
        assert!(rewritten.contains(placeholder));
        assert!(rewritten.contains("data-solid-island=\"MusicTrack\""));
        assert!(!rewritten.contains("bad()"));
        assert!(!rewritten.contains("data-solid-ssr"));
    }

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

        let rewritten = rewrite(&html, &images, &[], None).unwrap();

        assert!(rewritten.contains("class=\"terminal\""));
        assert!(rewritten.contains("data-language=\"command\""));
        assert!(rewritten.contains("class=\"md-img-container\" data-caption=\"Shot\""));
        assert!(rewritten.contains("<picture><source srcset=\"/media/image.webp\""));
        assert!(!rewritten.contains("directive"));
        assert!(!rewritten.contains("onerror"));
    }
}
