use serde::Deserialize;

#[derive(Deserialize)]
pub(crate) struct HtmlFixture {
    pub(crate) name: String,
    pub(crate) input: String,
    pub(crate) expected: String,
}

pub(crate) fn html_fixtures(raw: &str) -> Vec<HtmlFixture> {
    serde_json::from_str(raw).expect("valid HTML fixture JSON")
}
