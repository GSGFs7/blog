use serde::Deserialize;
use serde::de::DeserializeOwned;

#[derive(Deserialize)]
pub(crate) struct HtmlFixture {
    pub(crate) name: String,
    pub(crate) input: String,
    pub(crate) expected: String,
}

pub(crate) fn fixtures<T: DeserializeOwned>(raw: &str) -> Vec<T> {
    serde_json::from_str(raw).expect("valid HTML fixture JSON")
}

pub(crate) fn html_fixtures(raw: &str) -> Vec<HtmlFixture> {
    fixtures(raw)
}
