use markdown_it::MarkdownIt;
use markdown_it::parser::core::Root;
use markdown_it::plugins::cmark::block::heading::ATXHeading;
use markdown_it::plugins::cmark::block::lheading::SetextHeader;
use markdown_it::plugins::extra::front_matter::FrontMatter;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::builder::build;
use crate::types::{PyFrontMatter, PyRenderPlan};

#[pyclass(name = "MarkdownIt")]
pub(crate) struct PyMarkdownIt {
    inner: MarkdownIt,
}

#[pymethods]
impl PyMarkdownIt {
    #[new]
    fn new() -> Self {
        Self { inner: build() }
    }

    #[pyo3(signature = (src, *, include_toc = false, include_frontmatter = false))]
    fn prepare(
        &self,
        py: Python<'_>,
        src: &str,
        include_toc: bool,
        include_frontmatter: bool,
    ) -> PyResult<PyRenderPlan> {
        let root = self.inner.parse(src);

        let toc = if include_toc {
            extract_toc(py, &root)?
        } else {
            Vec::new()
        };

        let frontmatter = if include_frontmatter {
            root.cast::<Root>()
                .and_then(|root| root.ext.get::<FrontMatter>())
                .map(PyFrontMatter::from)
        } else {
            None
        };

        let html = root.render();

        Ok(PyRenderPlan::new(html, toc, frontmatter))
    }
}

fn extract_toc(py: Python<'_>, root: &markdown_it::Node) -> PyResult<Vec<Py<PyDict>>> {
    let mut toc = Vec::new();
    for node in &root.children {
        let level = node
            .cast::<ATXHeading>()
            .map(|heading| heading.level)
            .or_else(|| node.cast::<SetextHeader>().map(|heading| heading.level));
        let Some(level) = level else {
            continue;
        };
        let Some(slug) = node
            .attrs
            .iter()
            // must have a id attr
            .find(|(name, _)| *name == "id")
            .map(|(_, value)| value.clone())
        else {
            continue;
        };

        // e.g.
        // [{"level": 1, "slug": "first", "text": "First"},
        //  {"level": 2, "slug": "second", "text": "Second"}]
        let item = PyDict::new(py);
        item.set_item("level", level)?;
        item.set_item("slug", slug)?;
        item.set_item("text", node.collect_text())?;
        toc.push(item.unbind());
    }

    Ok(toc)
}
