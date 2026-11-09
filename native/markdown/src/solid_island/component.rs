#[derive(Clone, Copy)]
pub(super) enum Component {
    Counter,
    PythonRepl,
    PythonPlayground,
    Chart,
    Music,
    ModelViewer,
}

impl Component {
    pub(super) const ALL: [Self; 6] = [
        Self::Counter,
        Self::PythonRepl,
        Self::PythonPlayground,
        Self::Chart,
        Self::Music,
        Self::ModelViewer,
    ];

    pub(super) fn from_directive(name: &str) -> Option<Self> {
        Self::ALL
            .into_iter()
            .find(|component| component.aliases().contains(&name))
    }

    pub(super) fn aliases(&self) -> &'static [&'static str] {
        match self {
            Self::Counter => &["counter"],
            Self::PythonRepl => &["python-wasm", "python-repl"],
            Self::PythonPlayground => &["python-playground"],
            Self::Chart => &["chart", "charts"],
            Self::Music => &["music"],
            Self::ModelViewer => &["model"],
        }
    }

    pub(super) fn name(&self) -> &'static str {
        match self {
            Self::Music => "MusicTrack",
            Self::Counter => "Counter",
            Self::PythonRepl => "PythonREPL",
            Self::PythonPlayground => "PythonPlayground",
            Self::Chart => "Chart",
            Self::ModelViewer => "ModelViewer",
        }
    }

    fn allows_prop(&self, name: &str) -> bool {
        match self {
            Self::Music => name == "src",
            Self::Counter => name == "initial",
            Self::PythonRepl => false,
            Self::PythonPlayground => name == "source",
            Self::Chart => matches!(
                name,
                "title"
                    | "formula"
                    | "hide-input"
                    | "disable-drag"
                    | "x-min"
                    | "x-max"
                    | "y-min"
                    | "y-max"
            ),
            Self::ModelViewer => matches!(name, "src" | "alt"),
        }
    }

    pub(super) fn placeholder(&self) -> Option<&'static str> {
        match self {
            Self::Music => Some(""),
            Self::ModelViewer => {
                Some(r#"<span class="model-viewer-status">Scroll here to load the model</span>"#)
            }
            _ => None,
        }
    }

    pub(super) fn props_json(&self, attrs: impl IntoIterator<Item = (String, String)>) -> String {
        let props = attrs
            .into_iter()
            .filter_map(|(name, value)| {
                let name = name.to_ascii_lowercase();
                if !self.allows_prop(&name) {
                    return None;
                }
                let value = if matches!(self, Self::Music) {
                    html_escape::decode_html_entities(&value).into_owned()
                } else {
                    value
                };
                Some(format!(
                    "{}:{}",
                    serde_json::to_string(&name).expect("string serialization cannot fail"),
                    serde_json::to_string(&value).expect("string serialization cannot fail"),
                ))
            })
            .collect::<Vec<_>>()
            .join(",");
        format!("{{{props}}}")
    }
}
