use markdown_it::Node;
use markdown_it::plugins::extra::front_matter::{FrontMatter, FrontMatterKind};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[derive(Clone)]
#[pyclass(name = "FrontMatter", skip_from_py_object)]
pub(crate) struct PyFrontMatter {
    #[pyo3(get)]
    kind: String,
    #[pyo3(get)]
    raw: String,
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
        }
    }
}

#[pyclass(name = "RenderPlan", unsendable)]
pub(crate) struct PyRenderPlan {
    // one-time consumption
    root: Option<Node>,
    #[pyo3(get)]
    pub(crate) image_checksums: Vec<String>,
    #[pyo3(get)]
    pub(crate) toc: Vec<Py<PyDict>>,
    #[pyo3(get)]
    pub(crate) frontmatter: Option<PyFrontMatter>,
}

#[pymethods]
impl PyRenderPlan {
    #[pyo3(signature = (images = None))]
    fn finish(&mut self, images: Option<&Bound<'_, PyDict>>) -> PyResult<String> {
        let root = self
            .root
            .take()
            .ok_or_else(|| PyRuntimeError::new_err("render plan already finished"))?;

        let _ = images; // todo
        Ok(root.render())
    }
}

impl PyRenderPlan {
    pub(crate) fn new(
        root: Node,
        toc: Vec<Py<PyDict>>,
        frontmatter: Option<PyFrontMatter>,
    ) -> Self {
        Self {
            root: Some(root),
            image_checksums: Vec::new(),
            toc,
            frontmatter,
        }
    }
}
