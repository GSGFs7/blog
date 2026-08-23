use std::collections::HashMap;

use markdown_it::Node;
use markdown_it::plugins::extra::front_matter::{FrontMatter, FrontMatterKind};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyMapping, PyTuple};

use crate::error::MarkdownError;
use crate::suffix;
use crate::utils::parse_image_metadata;

#[derive(Debug)]
pub(crate) struct ImageMetadata {
    pub(crate) src: String,
    pub(crate) avif_src: Option<String>,
    pub(crate) webp_src: Option<String>,
    pub(crate) width: Option<u32>,
    pub(crate) height: Option<u32>,
    pub(crate) placeholder: Option<String>,
}

type ResolvedImages = HashMap<String, ImageMetadata>;

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

#[pyclass(name = "RenderPlan")]
pub(crate) struct PyRenderPlan {
    // one-time consumption
    root: Option<Node>,
    pub(crate) image_checksums: Vec<String>,
    pub(crate) image_picture_source_prefixes: Vec<String>,
    #[pyo3(get)]
    pub(crate) toc: Vec<Py<PyDict>>,
    #[pyo3(get)]
    pub(crate) frontmatter: Option<PyFrontMatter>,
}

#[pymethods]
impl PyRenderPlan {
    #[getter]
    fn image_checksums<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, self.image_checksums.iter())
    }

    #[pyo3(signature = (images = None))]
    fn finish(
        &mut self,
        py: Python<'_>,
        images: Option<&Bound<'_, PyMapping>>,
    ) -> PyResult<String> {
        if self.root.is_none() {
            return Err(PyRuntimeError::new_err("render plan already finished"));
        }

        let images = self.parse_images(images)?;

        let root = self.root.take().expect("checked above");
        let image_picture_source_prefixes = std::mem::take(&mut self.image_picture_source_prefixes);

        // release GIL
        py.detach(move || Self::render_and_rewrite(root, images, &image_picture_source_prefixes))
            .map_err(MarkdownError::into_pyerr)
    }
}

impl PyRenderPlan {
    pub(crate) fn new(
        root: Node,
        image_checksums: Vec<String>,
        image_picture_source_prefixes: Vec<String>,
        toc: Vec<Py<PyDict>>,
        frontmatter: Option<PyFrontMatter>,
    ) -> Self {
        Self {
            root: Some(root),
            image_checksums,
            image_picture_source_prefixes,
            toc,
            frontmatter,
        }
    }

    fn parse_images(&self, images: Option<&Bound<'_, PyMapping>>) -> PyResult<ResolvedImages> {
        let Some(images) = images else {
            return Ok(HashMap::new());
        };

        let mut resolved = HashMap::with_capacity(self.image_checksums.len());
        for checksum in &self.image_checksums {
            if !images.contains(checksum)? {
                continue;
            }

            let value = images.get_item(checksum)?;
            resolved.insert(checksum.clone(), parse_image_metadata(checksum, &value)?);
        }

        Ok(resolved)
    }

    fn render_and_rewrite(
        root: Node,
        images: ResolvedImages,
        image_picture_source_prefixes: &[String],
    ) -> Result<String, MarkdownError> {
        suffix::rewrite(&root.render(), &images, image_picture_source_prefixes)
            .map_err(|_| MarkdownError::RewriteFailed)
    }
}

#[cfg(test)]
mod tests {
    use pyo3::exceptions::{PyTypeError, PyValueError};

    use super::*;
    use crate::builder::build;

    fn plan_with_checksum(checksum: String) -> PyRenderPlan {
        PyRenderPlan::new(
            build().parse("hello"),
            vec![checksum],
            Vec::new(),
            Vec::new(),
            None,
        )
    }

    #[test]
    fn invalid_metadata_does_not_consume_plan() {
        Python::attach(|py| {
            let checksum = "a".repeat(64);
            let mut plan = plan_with_checksum(checksum.clone());
            let images = PyDict::new(py);
            images.set_item(&checksum, PyDict::new(py)).unwrap();
            let images = images.cast::<PyMapping>().unwrap();

            let error = plan.finish(py, Some(images)).unwrap_err();
            assert!(error.is_instance_of::<PyValueError>(py));

            let metadata = PyDict::new(py);
            metadata.set_item("src", "image.jpg").unwrap();
            images.set_item(&checksum, metadata).unwrap();

            assert_eq!(plan.finish(py, Some(images)).unwrap(), "<p>hello</p>\n");
        });
    }

    #[test]
    fn parses_owned_metadata_and_ignores_extras() {
        Python::attach(|py| {
            let checksum = "a".repeat(64);
            let extra_checksum = "b".repeat(64);
            let plan = plan_with_checksum(checksum.clone());
            let metadata = PyDict::new(py);
            metadata.set_item("src", "image.jpg").unwrap();
            metadata.set_item("avif_src", "image.avif").unwrap();
            metadata.set_item("webp_src", py.None()).unwrap();
            metadata.set_item("width", 640).unwrap();
            metadata.set_item("height", py.None()).unwrap();
            metadata
                .set_item("placeholder", "data:image/webp;base64,eA==")
                .unwrap();
            let images = PyDict::new(py);
            images.set_item(&checksum, metadata).unwrap();
            images
                .set_item(extra_checksum, Vec::<String>::new())
                .unwrap();

            let resolved = plan
                .parse_images(Some(images.cast::<PyMapping>().unwrap()))
                .unwrap();
            let image = resolved.get(&checksum).unwrap();
            assert_eq!(image.src, "image.jpg");
            assert_eq!(image.avif_src.as_deref(), Some("image.avif"));
            assert_eq!(image.webp_src, None);
            assert_eq!(image.width, Some(640));
            assert_eq!(image.height, None);
            assert_eq!(
                image.placeholder.as_deref(),
                Some("data:image/webp;base64,eA==")
            );
        });
    }

    #[test]
    fn rejects_invalid_metadata_types_and_values() {
        Python::attach(|py| {
            let checksum = "a".repeat(64);
            let plan = plan_with_checksum(checksum.clone());
            let metadata = PyDict::new(py);
            metadata.set_item("src", "image.jpg").unwrap();
            metadata.set_item("width", -1).unwrap();
            let images = PyDict::new(py);
            images.set_item(&checksum, metadata).unwrap();

            let error = plan
                .parse_images(Some(images.cast::<PyMapping>().unwrap()))
                .unwrap_err();
            assert!(error.is_instance_of::<PyValueError>(py));

            let metadata = PyDict::new(py);
            metadata.set_item("src", "image.jpg").unwrap();
            metadata.set_item("width", true).unwrap();
            images.set_item(&checksum, metadata).unwrap();
            let error = plan
                .parse_images(Some(images.cast::<PyMapping>().unwrap()))
                .unwrap_err();
            assert!(error.is_instance_of::<PyTypeError>(py));

            images.set_item(&checksum, Vec::<String>::new()).unwrap();
            let error = plan
                .parse_images(Some(images.cast::<PyMapping>().unwrap()))
                .unwrap_err();
            assert!(error.is_instance_of::<PyTypeError>(py));
        });
    }

    #[test]
    fn keeps_picture_source_prefixes_owned_by_plan() {
        let plan = PyRenderPlan::new(
            build().parse("hello"),
            Vec::new(),
            vec!["https://uploads.example/raw/".to_owned()],
            Vec::new(),
            None,
        );

        assert_eq!(
            plan.image_picture_source_prefixes,
            vec!["https://uploads.example/raw/"]
        );
    }
}
