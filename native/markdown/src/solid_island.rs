mod component;
mod directives;
mod raw_html;

// syntax 1, `::counter{initial="0"}`
pub(crate) use directives::add;
// syntax 2, `<div class="directive counter" initial="0"></div>`
pub(crate) use raw_html::{inject_music_placeholder, rewrite_raw_html};

#[cfg(test)]
mod tests;
