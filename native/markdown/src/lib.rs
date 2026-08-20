pub(crate) mod builder;
pub(crate) mod markdown_it_py;
pub(crate) mod types;

use pyo3::prelude::*;

use crate::markdown_it_py::PyMarkdownIt;
use crate::types::{PyFrontMatter, PyRenderPlan};

#[pymodule]
fn _markdown_it_rs_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyMarkdownIt>()?;
    m.add_class::<PyFrontMatter>()?;
    m.add_class::<PyRenderPlan>()?;
    Ok(())
}
