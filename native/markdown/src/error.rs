use pyo3::PyErr;
use pyo3::exceptions::{PyRuntimeError, PyValueError};

#[derive(Debug)]
pub(crate) enum MarkdownError {
    InvalidYamlFrontmatter,
    InvalidTomlFrontmatter,
    FrontmatterMustBeMapping,
    FrontmatterKeysMustBeStrings,
    FrontmatterFloatsMustBeFinite,
    UnsupportedFrontmatterValue,
    RewriteFailed,
}

impl MarkdownError {
    pub(crate) fn into_pyerr(self) -> PyErr {
        match self {
            MarkdownError::InvalidYamlFrontmatter => {
                PyValueError::new_err("invalid YAML frontmatter")
            }
            MarkdownError::InvalidTomlFrontmatter => {
                PyValueError::new_err("invalid TOML frontmatter")
            }
            MarkdownError::FrontmatterMustBeMapping => {
                PyValueError::new_err("frontmatter must be a mapping")
            }
            MarkdownError::FrontmatterKeysMustBeStrings => {
                PyValueError::new_err("frontmatter mapping keys must be strings")
            }
            MarkdownError::FrontmatterFloatsMustBeFinite => {
                PyValueError::new_err("frontmatter floats must be finite")
            }
            MarkdownError::UnsupportedFrontmatterValue => {
                PyValueError::new_err("unsupported frontmatter value")
            }
            MarkdownError::RewriteFailed => PyRuntimeError::new_err("markdown HTML rewrite failed"),
        }
    }
}
