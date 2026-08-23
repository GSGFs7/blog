use std::cell::RefCell;
use std::ops::Range;
use std::rc::Rc;

use html_escape::decode_html_entities;
use lol_html::errors::RewritingError;
use lol_html::html_content::Element;
use lol_html::{RewriteStrSettings, element, end_tag, rewrite_str};

use crate::rewriter::escape_html;

#[derive(Debug)]
struct Picture {
    start: usize,
    end: Option<usize>,
}

#[derive(Debug)]
struct Image {
    range: Range<usize>,
    caption: String,
}

struct Wrapper {
    range: Range<usize>,
    caption: String,
}

pub(crate) fn rewrite(html: &str) -> Result<String, RewritingError> {
    let pictures = Rc::new(RefCell::new(Vec::<Picture>::new()));
    let images = Rc::new(RefCell::new(Vec::<Image>::new()));
    let picture_nodes = pictures.clone();
    let image_nodes = images.clone();

    rewrite_str(
        html,
        RewriteStrSettings::new()
            .append_element_content_handler(element!("picture", move |element: &mut Element<
                '_,
                '_,
            >| {
                if element.tag_name_preserve_case() != "picture" {
                    return Ok(());
                }
                let index = {
                    let mut pictures = picture_nodes.borrow_mut();
                    let index = pictures.len();
                    pictures.push(Picture {
                        start: element.start_tag().source_location().bytes().start,
                        end: None,
                    });
                    index
                };
                let picture_nodes = picture_nodes.clone();
                element.on_end_tag(end_tag!(move |end| {
                    if end.name_preserve_case() == "picture" {
                        picture_nodes.borrow_mut()[index].end =
                            Some(end.source_location().bytes().end);
                    }
                    Ok(())
                }))
            }))
            .append_element_content_handler(element!("img", move |element: &mut Element<
                '_,
                '_,
            >| {
                if element.tag_name_preserve_case() != "img" {
                    return Ok(());
                }
                let alt = decoded_attribute(element, "alt").unwrap_or_default();
                let title = decoded_attribute(element, "title");
                image_nodes.borrow_mut().push(Image {
                    range: element.start_tag().source_location().bytes(),
                    caption: title.filter(|title| !title.is_empty()).unwrap_or(alt),
                });
                Ok(())
            })),
    )?;

    let pictures = Rc::try_unwrap(pictures)
        .expect("rewrite handlers released")
        .into_inner();
    let images = Rc::try_unwrap(images)
        .expect("rewrite handlers released")
        .into_inner();
    Ok(apply_wrappers(html, pictures, images))
}

fn decoded_attribute(element: &Element<'_, '_>, name: &str) -> Option<String> {
    element
        .get_attribute(name)
        .map(|value| decode_html_entities(&value).into_owned())
}

fn apply_wrappers(html: &str, pictures: Vec<Picture>, images: Vec<Image>) -> String {
    let picture_ranges: Vec<_> = pictures
        .into_iter()
        .filter_map(|picture| {
            let end = picture.end?;
            let range = picture.start..end;
            (!html[range.clone()].contains('\n')).then_some(range)
        })
        .collect();
    let mut wrappers: Vec<_> = picture_ranges
        .iter()
        .map(|range| Wrapper {
            range: range.clone(),
            caption: images
                .iter()
                .find(|image| range.contains(&image.range.start))
                .map(|image| image.caption.clone())
                .unwrap_or_default(),
        })
        .collect();
    wrappers.extend(
        images
            .into_iter()
            .filter(|image| {
                !picture_ranges
                    .iter()
                    .any(|range| range.contains(&image.range.start))
            })
            .map(|image| Wrapper {
                range: image.range,
                caption: image.caption,
            }),
    );
    wrappers.sort_by_key(|wrapper| wrapper.range.start);

    let mut output = html.to_owned();
    for wrapper in wrappers.into_iter().rev() {
        output.insert_str(wrapper.range.end, "</span>");
        output.insert_str(
            wrapper.range.start,
            &format!(
                "<span class=\"md-img-container\" data-caption=\"{}\">",
                escape_html(&wrapper.caption)
            ),
        );
    }
    output
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    use super::*;
    use crate::sanitizer::sanitize;
    use crate::test_support::fixtures;
    use crate::{code_language, solid_island, terminal};

    #[derive(Deserialize)]
    struct ImageWrapperFixture {
        name: String,
        input: String,
        image: String,
        sanitized: String,
    }

    #[test]
    fn matches_frozen_python_fixtures() {
        let fixtures: Vec<ImageWrapperFixture> =
            fixtures(include_str!("../tests/fixtures/image_wrapper.json"));
        for fixture in fixtures {
            let image = rewrite(&fixture.input).unwrap();
            assert_eq!(image, fixture.image, "fixture: {}", fixture.name);
            let code = code_language::rewrite(&image).unwrap();
            let terminal = terminal::rewrite(&code).unwrap();
            let solid = solid_island::rewrite(&terminal).unwrap();
            assert_eq!(
                sanitize(&solid),
                fixture.sanitized,
                "sanitized fixture: {}",
                fixture.name
            );
        }
    }

    #[test]
    fn reads_caption_from_structured_attributes() {
        let html = rewrite("<img src='a.jpg' alt='Alt' title='Single quote'>").unwrap();

        assert_eq!(
            html,
            "<span class=\"md-img-container\" data-caption=\"Single quote\"><img src='a.jpg' alt='Alt' title='Single quote'></span>"
        );
    }
}
