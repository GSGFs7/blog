use std::cell::RefCell;
use std::ops::Range;
use std::rc::Rc;
use std::sync::LazyLock;

use lol_html::errors::RewritingError;
use lol_html::html_content::Element;
use lol_html::{RewriteStrSettings, element, rewrite_str};
use regex::Regex;

static LANGUAGE_CLASS: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"\blanguage-([^\s"]+)$"#).unwrap());

#[derive(Debug)]
struct Candidate {
    start_tag: Range<usize>,
    code_start: usize,
    language: Option<String>,
}

pub(crate) fn rewrite(html: &str) -> Result<String, RewritingError> {
    let mut candidates = find_candidates(html)?;
    candidates.sort_by_key(|candidate| candidate.start_tag.start);

    let mut output = html.to_owned();
    for candidate in candidates.into_iter().rev() {
        output.replace_range(candidate.start_tag.end..candidate.code_start, "");
        output.insert_str(
            candidate.start_tag.start + "<pre".len(),
            &format!(
                " data-language=\"{}\"",
                candidate.language.expect("filtered candidate")
            ),
        );
    }
    Ok(output)
}

fn find_candidates(html: &str) -> Result<Vec<Candidate>, RewritingError> {
    let candidates = Rc::new(RefCell::new(Vec::<Candidate>::new()));
    let pre_candidates = candidates.clone();
    let code_candidates = candidates.clone();

    rewrite_str(
        html,
        RewriteStrSettings::new()
            .append_element_content_handler(element!("pre", move |element: &mut Element<
                '_,
                '_,
            >| {
                if element.tag_name_preserve_case() == "pre" {
                    pre_candidates.borrow_mut().push(Candidate {
                        start_tag: element.start_tag().source_location().bytes(),
                        code_start: 0,
                        language: None,
                    });
                }
                Ok(())
            }))
            .append_element_content_handler(element!(
                "pre > code[class]",
                move |element: &mut Element<'_, '_>| {
                    if element.tag_name_preserve_case() != "code" {
                        return Ok(());
                    }
                    let Some(class) = element.get_attribute("class") else {
                        return Ok(());
                    };
                    let Some(language) = LANGUAGE_CLASS
                        .captures(&class)
                        .and_then(|captures| captures.get(1))
                        .map(|capture| capture.as_str().to_owned())
                    else {
                        return Ok(());
                    };
                    let code_start = element.start_tag().source_location().bytes().start;
                    let mut candidates = code_candidates.borrow_mut();
                    let Some(candidate) = candidates.iter_mut().rev().find(|candidate| {
                        candidate.language.is_none()
                            && candidate.start_tag.end <= code_start
                            && html[candidate.start_tag.end..code_start]
                                .chars()
                                .all(char::is_whitespace)
                    }) else {
                        return Ok(());
                    };
                    candidate.code_start = code_start;
                    candidate.language = Some(language);
                    Ok(())
                }
            )),
    )?;

    let candidates = Rc::try_unwrap(candidates)
        .expect("rewrite handlers released")
        .into_inner()
        .into_iter()
        .filter(|candidate| candidate.language.is_some())
        .collect();
    Ok(candidates)
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    use super::*;
    use crate::sanitizer::sanitize;
    use crate::test_support::fixtures;
    use crate::{solid_island, terminal};

    #[derive(Deserialize)]
    struct CodeLanguageFixture {
        name: String,
        input: String,
        code: String,
        terminal: String,
        solid: String,
        sanitized: String,
    }

    #[test]
    fn matches_frozen_python_fixtures() {
        let fixtures: Vec<CodeLanguageFixture> =
            fixtures(include_str!("../tests/fixtures/code_language.json"));
        for fixture in fixtures {
            let code = rewrite(&fixture.input).unwrap();
            assert_eq!(code, fixture.code, "fixture: {}", fixture.name);
            let terminal = terminal::rewrite(&code).unwrap();
            assert_eq!(
                terminal, fixture.terminal,
                "terminal fixture: {}",
                fixture.name
            );
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
}
