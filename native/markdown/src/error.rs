use pyo3::PyErr;
use pyo3::exceptions::PyRuntimeError;

#[allow(dead_code)]
pub(crate) enum MarkdownError {
    RewriteFailed,
}

impl MarkdownError {
    pub(crate) fn into_pyerr(self) -> PyErr {
        match self {
            MarkdownError::RewriteFailed => PyRuntimeError::new_err("markdown HTML rewrite failed"),
        }
    }
}
