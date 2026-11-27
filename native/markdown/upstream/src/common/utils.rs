//! Character classification, HTML entity decoding, and Markdown unescaping helpers.

use std::borrow::Cow;
use std::collections::HashMap;
use std::sync::LazyLock;

use regex::Regex;

/// Character class for the whitespace and line terminators recognized by
/// JavaScript's `String.prototype.trim()` and regexp `\s`.
///
/// This is Rust's Unicode `White_Space` plus BOM (U+FEFF) and minus NEL
/// (U+0085); JavaScript uses this set for `trim()`, `/\s/` and markdown-it's
/// HTML info strings and table cells. Markdown syntax itself uses Rust's
/// `char::is_whitespace` instead, so keep the two apart.
pub(crate) const JS_WHITESPACE_CLASS: &str = r"[\s\u{FEFF}--\u{0085}]";

/// The whitespace and line terminators recognized by JavaScript's String.trim().
///
/// Predicate form of [`JS_WHITESPACE_CLASS`].
#[inline]
pub(crate) fn is_js_whitespace(ch: char) -> bool {
    if ch.is_ascii() {
        return matches!(ch, ' ' | '\t' | '\n' | '\u{b}' | '\u{c}' | '\r');
    }

    ch == '\u{feff}' || (ch.is_whitespace() && ch != '\u{85}')
}

/// Whether `str` contains only JavaScript whitespace, i.e. `!str.trim()`.
pub(crate) fn is_js_blank(str: &str) -> bool {
    str.chars().all(is_js_whitespace)
}

/// Markdown whitespace used by markdown-it's delimiter and quote classifiers:
/// Unicode Zs plus ASCII tab, LF, VT, FF, and CR. This differs from JavaScript
/// regex `\s` and Rust's Unicode `White_Space` (notably for NEL, LS, PS, and BOM).
pub(crate) fn is_markdown_whitespace(ch: char) -> bool {
    matches!(ch, '\t'..='\r' | ' ' | '\u{a0}' | '\u{1680}' |
        '\u{2000}'..='\u{200a}' | '\u{202f}' | '\u{205f}' | '\u{3000}')
}

/// Checks whether a given character should count as punctuation.
///
/// Used to determine word boundaries, matching `isPunctChar` from markdown-it.js.
pub fn is_punct_char(ch: char) -> bool {
    use unicode_general_category::GeneralCategory::*;
    use unicode_general_category::get_general_category;

    matches!(
        get_general_category(ch),
        // P
        ConnectorPunctuation | DashPunctuation | OpenPunctuation | ClosePunctuation |
        InitialPunctuation | FinalPunctuation | OtherPunctuation |
        // S (in CommonMark 0.31, symbol also refers to punctuation)
        MathSymbol | CurrencySymbol | ModifierSymbol | OtherSymbol
    )
}

/// Return true if a `code` you got from `&#xHHHH;` entity is a valid charcode.
///
/// It returns false for surrogates and non-printables, so it's a subset of `char::from_u32`.
/// For example, it returns false for 0xFDD0, which is a valid character, but not safe to
/// render on the screen due to turning you into stone, as per <https://xkcd.com/380/>
/// ```
/// # use markdown_it::common::utils::is_valid_entity_code;
/// assert_eq!(is_valid_entity_code(1), false);
/// assert_eq!(is_valid_entity_code(32), true);
/// ```
#[allow(clippy::manual_range_contains)]
pub fn is_valid_entity_code(code: u32) -> bool {
    // broken sequence
    if code >= 0xD800 && code <= 0xDFFF {
        return false;
    }
    // never used
    if code >= 0xFDD0 && code <= 0xFDEF {
        return false;
    }
    if (code & 0xFFFF) == 0xFFFF || (code & 0xFFFF) == 0xFFFE {
        return false;
    }
    // control codes
    if code <= 0x08 {
        return false;
    }
    if code == 0x0B {
        return false;
    }
    if code >= 0x0E && code <= 0x1F {
        return false;
    }
    if code >= 0x7F && code <= 0x9F {
        return false;
    }
    // out of range
    if code > 0x10FFFF {
        return false;
    }
    true
}

/// Check if "&xxxx;" string is a valid HTML entity, return character it represents.
/// ```
/// # use markdown_it::common::utils::get_entity_from_str;
/// assert_eq!(get_entity_from_str("&amp;"), Some("&"));
/// assert_eq!(get_entity_from_str("&xxx;"), None);
/// ```
pub fn get_entity_from_str(str: &str) -> Option<&'static str> {
    static ENTITIES_HASH: LazyLock<HashMap<&'static str, &'static str>> = LazyLock::new(|| {
        let mut mapping = HashMap::new();
        for e in &entities::ENTITIES {
            if e.entity.ends_with(';') {
                mapping.insert(e.entity, e.characters);
            }
        }
        mapping
    });

    ENTITIES_HASH.get(str).copied()
}

/// Unescape both entities (`&quot; -> "`) and backslash escapes (`\" -> "`).
/// ```
/// # use markdown_it::common::utils::unescape_all;
/// assert_eq!(unescape_all("&amp;"), "&");
/// assert_eq!(unescape_all("\\&"), "&");
/// ```
pub fn unescape_all(str: &str) -> Cow<'_, str> {
    const UNESCAPE_MD_RE: &str = r##"\\([!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])"##;
    const ENTITY_RE: &str = r##"&([A-Za-z#][A-Za-z0-9]{1,31});"##;
    static UNESCAPE_ALL_RE: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(&format!("{UNESCAPE_MD_RE}|{ENTITY_RE}")).unwrap());

    if memchr::memchr2(b'\\', b'&', str.as_bytes()).is_none() {
        return Cow::Borrowed(str);
    }

    UNESCAPE_ALL_RE.replace_all(str, |captures: &regex::Captures| {
        let s = captures.get(0).unwrap().as_str();
        if let Some(m) = captures.get(1) {
            // \" -> "
            m.as_str().to_owned()
        } else if let Some(replacement) = replace_entity_pattern(s) {
            // &quot; -> "
            replacement
        } else {
            s.to_owned()
        }
    })
}

#[allow(clippy::from_str_radix_10)]
fn replace_entity_pattern(str: &str) -> Option<String> {
    static DIGITAL_ENTITY_TEST_RE: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r#"(?i)^&#(x[a-f0-9]{1,8}|[0-9]{1,8});$"#).unwrap());

    if let Some(entity) = get_entity_from_str(str) {
        Some((*entity).to_owned())
    } else if let Some(captures) = DIGITAL_ENTITY_TEST_RE.captures(str) {
        let str = captures.get(1).unwrap().as_str();
        let code = if str.starts_with('x') || str.starts_with('X') {
            u32::from_str_radix(&str[1..], 16).unwrap()
        } else {
            u32::from_str_radix(str, 10).unwrap()
        };

        if is_valid_entity_code(code) {
            Some(char::from_u32(code).unwrap().into())
        } else {
            None
        }
    } else {
        // markdown-it's unescapeAll() falls back to decodeHTMLStrict() for
        // entities that its own numeric regex rejects.
        decode_long_numeric_entity(str)
    }
}

fn decode_long_numeric_entity(str: &str) -> Option<String> {
    /// Windows-1252 replacements for C1 controls in malformed numeric entities.
    ///
    /// markdown-it falls back to `entities.decodeHTMLStrict()` when a numeric
    /// reference is too long for its own fast-path regex. That fallback applies
    /// the HTML C1 remapping, unlike the regular `is_valid_entity_code` path.
    const C1_REPLACEMENTS: [u32; 32] = [
        8364, 0, 8218, 402, 8222, 8230, 8224, 8225, 710, 8240, 352, 8249, 338, 0, 381, 0, 0, 8216,
        8217, 8220, 8221, 8226, 8211, 8212, 732, 8482, 353, 8250, 339, 0, 382, 376,
    ];

    let body = str.strip_prefix("&#")?.strip_suffix(';')?;
    let (digits, radix) = match body.strip_prefix('x').or_else(|| body.strip_prefix('X')) {
        Some(hex) => (hex, 16),
        None => (body, 10),
    };
    if digits.is_empty() {
        return None;
    }

    let mut value = 0u64;
    for byte in digits.bytes() {
        let digit = match byte {
            b'0'..=b'9' => u64::from(byte - b'0'),
            b'a'..=b'f' => u64::from(byte - b'a' + 10),
            b'A'..=b'F' => u64::from(byte - b'A' + 10),
            _ => return None,
        };
        if digit >= radix {
            return None;
        }
        value = value.saturating_mul(radix).saturating_add(digit);
    }

    let code = if value == 0 || value > 0x10FFFF || (0xD800..=0xDFFF).contains(&value) {
        0xFFFD
    } else if (128..=159).contains(&value) {
        let replacement = C1_REPLACEMENTS[(value - 128) as usize];
        if replacement == 0 {
            value as u32
        } else {
            replacement
        }
    } else {
        value as u32
    };

    char::from_u32(code).map(|c| c.to_string())
}

#[cfg(test)]
mod tests {
    use super::{is_js_blank, is_js_whitespace, replace_entity_pattern, unescape_all};

    #[test]
    fn js_whitespace_matches_javascript_trim() {
        for ch in [
            ' ', '\t', '\n', '\r', '\u{b}', '\u{c}', '\u{a0}', '\u{2028}', '\u{2029}',
        ] {
            assert!(is_js_whitespace(ch), "{ch:?}");
        }
        // BOM is whitespace for JavaScript, NEL is not.
        assert!(is_js_whitespace('\u{feff}'));
        assert!(!is_js_whitespace('\u{85}'));
        assert!(!is_js_whitespace('\u{200b}'));

        assert!(is_js_blank("\u{feff}\u{a0}"));
        assert!(!is_js_blank("\u{85}"));
        assert!(!is_js_blank(" x "));
    }

    #[test]
    fn test_replace_entity_pattern() {
        assert_eq!(replace_entity_pattern("&amp;"), Some("&".into()));
        assert_eq!(replace_entity_pattern("&euro;"), Some("€".into()));
        assert_eq!(replace_entity_pattern("&#8212;"), Some("—".into()));
        assert_eq!(replace_entity_pattern("&#x2014;"), Some("—".into()));
        assert_eq!(replace_entity_pattern("&#X20;"), Some(" ".into()));
        assert_eq!(replace_entity_pattern("&#x3F;"), Some("?".into()));
        assert_eq!(replace_entity_pattern("&ffff;"), None);
        assert_eq!(replace_entity_pattern("&#3F;"), None);
        assert_eq!(replace_entity_pattern("&#xGG;"), None);
        assert_eq!(
            replace_entity_pattern("&#xfffffffff;"),
            Some("\u{FFFD}".into())
        );
        assert_eq!(replace_entity_pattern("&#000000065;"), Some("A".into()));
        assert_eq!(replace_entity_pattern("&#000000128;"), Some("€".into()));
    }

    #[test]
    fn test_unescape_all_simple() {
        assert_eq!(unescape_all("&amp;"), "&");
        assert_eq!(unescape_all("\\&"), "&");
    }

    #[test]
    fn test_unescape_all_xss() {
        assert_eq!(
            unescape_all(r#"javascript&#x3A;alert(1)"#),
            r#"javascript:alert(1)"#
        );

        assert_eq!(
            unescape_all(r#"&#74;avascript:alert(1)"#),
            r#"Javascript:alert(1)"#
        );

        assert_eq!(
            unescape_all(r#"&#x26;#74;avascript:alert(1)"#),
            r#"&#74;avascript:alert(1)"#
        );

        assert_eq!(
            unescape_all(r#"\&#74;avascript:alert(1)"#),
            r#"&#74;avascript:alert(1)"#
        );

        assert_eq!(
            unescape_all(
                r#"&#34;&#62;&#60;script&#62;alert&#40;&#34;xss&#34;&#41;&#60;/script&#62;"#
            ),
            r#""><script>alert("xss")</script>"#
        );
    }
}
