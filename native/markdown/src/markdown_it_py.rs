use std::collections::HashSet;

use markdown_it::MarkdownIt;
use markdown_it::parser::core::Root;
use markdown_it::plugins::cmark::block::heading::ATXHeading;
use markdown_it::plugins::cmark::block::lheading::SetextHeader;
use markdown_it::plugins::cmark::inline::image::Image;
use markdown_it::plugins::extra::front_matter::FrontMatter;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::builder::build;
use crate::image_optimizer::extract_checksum;
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

    #[pyo3(signature = (src, *, include_toc = false, include_frontmatter = false, image_picture_source_prefixes = Vec::new()))]
    fn prepare(
        &self,
        py: Python<'_>,
        src: &str,
        include_toc: bool,
        include_frontmatter: bool,
        image_picture_source_prefixes: Vec<String>,
    ) -> PyResult<PyRenderPlan> {
        let src = src.to_owned();
        // release GIL
        let root = py.detach(|| self.inner.parse(&src));

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

        let image_checksums = collect_image_checksums(&root);

        Ok(PyRenderPlan::new(
            root,
            image_checksums,
            image_picture_source_prefixes,
            toc,
            frontmatter,
        ))
    }
}

// HTML blocks are not considered for the time being.
fn collect_image_checksums(root: &markdown_it::Node) -> Vec<String> {
    let mut checksums = Vec::new();
    let mut seen = HashSet::new();
    root.walk(|node, _| {
        let Some(image) = node.cast::<Image>() else {
            return;
        };
        let Some(checksum) = extract_checksum(&image.url) else {
            return;
        };
        if seen.insert(checksum.clone()) {
            checksums.push(checksum);
        }
    });
    checksums
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
