use std::cell::RefCell;
use std::ops::Range;
use std::rc::Rc;

use lol_html::errors::RewritingError;
use lol_html::html_content::Element;
use lol_html::{RewriteStrSettings, element, end_tag, rewrite_str};
use url::{Host, Url};

use crate::rewriter::escape_html;

#[derive(Debug)]
struct Link {
    content: Range<usize>,
    domain: String,
    already_wrapped: bool,
}

pub(crate) fn rewrite(html: &str) -> Result<String, RewritingError> {
    let links = Rc::new(RefCell::new(Vec::<Link>::new()));
    let active_links = Rc::new(RefCell::new(Vec::<usize>::new()));
    let anchor_links = links.clone();
    let anchor_active = active_links.clone();
    let span_links = links.clone();
    let span_active = active_links.clone();

    rewrite_str(
        html,
        RewriteStrSettings::new()
            .append_element_content_handler(element!("a[href]", move |element: &mut Element<
                '_,
                '_,
            >| {
                let Some(href) = element.get_attribute("href") else {
                    return Ok(());
                };
                let Some(domain) = domain(&href) else {
                    return Ok(());
                };
                let index = {
                    let mut links = anchor_links.borrow_mut();
                    let index = links.len();
                    let start = element.start_tag().source_location().bytes().end;
                    links.push(Link {
                        content: start..start,
                        domain,
                        already_wrapped: false,
                    });
                    index
                };
                anchor_active.borrow_mut().push(index);
                let anchor_links = anchor_links.clone();
                let anchor_active = anchor_active.clone();
                element.on_end_tag(end_tag!(move |end| {
                    anchor_links.borrow_mut()[index].content.end =
                        end.source_location().bytes().start;
                    let mut active = anchor_active.borrow_mut();
                    if active.last() == Some(&index) {
                        active.pop();
                    } else {
                        active.retain(|active_index| *active_index != index);
                    }
                    Ok(())
                }))
            }))
            .append_element_content_handler(element!(
                "span[data-domain]",
                move |_: &mut Element<'_, '_>| {
                    let Some(index) = span_active.borrow().last().copied() else {
                        return Ok(());
                    };
                    span_links.borrow_mut()[index].already_wrapped = true;
                    Ok(())
                }
            )),
    )?;

    let mut links = Rc::try_unwrap(links)
        .expect("rewrite handlers released")
        .into_inner();
    links.retain(|link| !link.already_wrapped && !link.content.is_empty());
    links.sort_by_key(|link| link.content.start);

    let mut output = html.to_owned();
    for link in links.into_iter().rev() {
        output.insert_str(link.content.end, "</span>");
        output.insert_str(
            link.content.start,
            &format!("<span data-domain=\"{}\">", escape_html(&link.domain)),
        );
    }
    Ok(output)
}

fn domain(href: &str) -> Option<String> {
    let url = Url::parse(href).ok()?;
    if !matches!(url.scheme(), "http" | "https") {
        return None;
    }
    match url.host()? {
        Host::Domain(domain) => Some(domain.to_owned()),
        Host::Ipv4(address) => Some(address.to_string()),
        Host::Ipv6(address) => Some(address.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wraps_http_links_using_standard_hostnames() {
        let html = rewrite(
            "<a href=\"https://user:password@example.com:8443/path\">private</a>\
             <a href=\"https://[2001:db8::1]:8443/path\">ipv6</a>\
             <a href=\"https://例子.测试/path\">idn</a>",
        )
        .unwrap();

        assert!(html.contains("<span data-domain=\"example.com\">private</span>"));
        assert!(html.contains("<span data-domain=\"2001:db8::1\">ipv6</span>"));
        assert!(html.contains("<span data-domain=\"xn--fsqu00a.xn--0zwm56d\">idn</span>"));
    }

    #[test]
    fn ignores_non_http_invalid_and_already_wrapped_links() {
        let input = "<a href=\"mailto:test@example.com\">mail</a>\
                     <a href=\"https://[invalid\">invalid</a>\
                     <a href=\"https://example.com\"><span data-domain=\"example.com\">done</span></a>";

        assert_eq!(rewrite(input).unwrap(), input);
    }

    #[test]
    fn leaves_malformed_links_without_end_tags_unchanged() {
        let input = "<a href=\"https://example.com\">open";

        assert_eq!(rewrite(input).unwrap(), input);
    }
}
