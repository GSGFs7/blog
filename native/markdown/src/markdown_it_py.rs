use std::collections::HashSet;
use std::sync::Arc;

use markdown_it::plugins::cmark::block::heading::ATXHeading;
use markdown_it::plugins::cmark::block::lheading::SetextHeader;
use markdown_it::plugins::cmark::inline::image::Image;
use markdown_it::plugins::cmark::inline::newline::Softbreak;
use markdown_it::{Document, MarkdownIt, NodeId, StructuralEvent, Text, TextSpecial};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::builder::build;
use crate::frontmatter;
use crate::image_optimizer::extract_checksum;
use crate::types::PyRenderPlan;

#[pyclass(name = "MarkdownIt")]
pub(crate) struct PyMarkdownIt {
    inner: Arc<MarkdownIt>,
}

#[pymethods]
impl PyMarkdownIt {
    #[new]
    fn new() -> Self {
        Self {
            inner: Arc::new(build()),
        }
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
        let (document, frontmatter) = py.detach(|| {
            let document = self.inner.parse(&src);
            let frontmatter = include_frontmatter
                .then(|| frontmatter::parse(&document))
                .transpose()
                .map(|value| value.flatten());
            (document, frontmatter)
        });
        let frontmatter = frontmatter
            .map_err(|error| error.into_pyerr())
            .and_then(|value| frontmatter::into_python(py, value))?;

        let toc = if include_toc {
            extract_toc(py, &document)?
        } else {
            Vec::new()
        };

        let image_checksums = collect_image_checksums(&document);

        Ok(PyRenderPlan::new(
            document,
            Arc::clone(&self.inner),
            image_checksums,
            image_picture_source_prefixes,
            toc,
            frontmatter,
        ))
    }
}

// HTML blocks are not considered for the time being.
fn collect_image_checksums(document: &Document) -> Vec<String> {
    let mut checksums = Vec::new();
    let mut seen = HashSet::new();
    for event in document.events(document.root()) {
        let node = match event {
            StructuralEvent::Enter(node) | StructuralEvent::Leaf(node) => node,
            StructuralEvent::Exit(_) => continue,
        };
        let Some(image) = node.cast::<Image>() else {
            continue;
        };
        let Some(checksum) = extract_checksum(&image.url) else {
            continue;
        };
        if seen.insert(checksum.clone()) {
            checksums.push(checksum);
        }
    }
    checksums
}

fn extract_toc(py: Python<'_>, document: &Document) -> PyResult<Vec<Py<PyDict>>> {
    let mut toc = Vec::new();
    for &id in document.children(document.root()) {
        let node = document.node(id);
        let level = node
            .cast::<ATXHeading>()
            .map(|heading| heading.level)
            .or_else(|| node.cast::<SetextHeader>().map(|heading| heading.level));
        let Some(level) = level else {
            continue;
        };
        let Some(slug) = node
            .attrs()
            .iter()
            // must have a id attr
            .find(|(name, _)| name == "id")
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
        item.set_item("text", collect_text(document, id))?;
        toc.push(item.unbind());
    }

    Ok(toc)
}

fn collect_text(document: &Document, root: NodeId) -> String {
    let mut text = String::new();
    for event in document.events(root) {
        let node = match event {
            StructuralEvent::Enter(node) | StructuralEvent::Leaf(node) => node,
            StructuralEvent::Exit(_) => continue,
        };

        if let Some(value) = node.cast::<Text>() {
            text.push_str(&value.content);
        } else if let Some(value) = node.cast::<TextSpecial>() {
            text.push_str(&value.content);
        } else if node.is::<Softbreak>() {
            text.push('\n');
        }
    }
    text
}
