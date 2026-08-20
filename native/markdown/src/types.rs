use markdown_it::plugins::extra::front_matter::{FrontMatter, FrontMatterKind};
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[derive(Clone)]
#[pyclass(name = "FrontMatter", skip_from_py_object)]
pub(crate) struct PyFrontMatter {
    #[pyo3(get)]
    kind: String,
    #[pyo3(get)]
    raw: String,
    #[pyo3(get)]
    start_line: usize,
    #[pyo3(get)]
    end_line: usize,
}

#[pyclass(name = "MarkdownOutput")]
pub(crate) struct PyMarkdownOutput {
    #[pyo3(get)]
    pub(crate) html: String,
    #[pyo3(get)]
    pub(crate) frontmatter: Option<PyFrontMatter>,
}

#[pyclass(name = "RenderPlan", unsendable)]
pub(crate) struct PyRenderPlan {
    #[pyo3(get)]
    pub(crate) image_checksums: Vec<String>,
    #[pyo3(get)]
    pub(crate) toc: Vec<Py<PyDict>>,
    #[pyo3(get)]
    pub(crate) frontmatter: Option<PyFrontMatter>,
    html: String,
}

#[pymethods]
impl PyRenderPlan {
    #[pyo3(signature = (images = None))]
    fn finish(&self, images: Option<&Bound<'_, PyDict>>) -> String {
        let _ = images; // todo
        self.html.clone()
    }
}

impl PyRenderPlan {
    pub(crate) fn new(
        html: String,
        toc: Vec<Py<PyDict>>,
        frontmatter: Option<PyFrontMatter>,
    ) -> Self {
        Self {
            image_checksums: Vec::new(),
            toc,
            frontmatter,
            html,
        }
    }
}

impl From<&FrontMatter> for PyFrontMatter {
    fn from(front_matter: &FrontMatter) -> Self {
        let kind = match front_matter.kind {
            FrontMatterKind::Yaml => "yaml",
            FrontMatterKind::Toml => "toml",
        };

        Self {
            kind: kind.to_owned(),
            raw: front_matter.raw.clone(),
            start_line: front_matter.start_line,
            end_line: front_matter.end_line,
        }
    }
}
