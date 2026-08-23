pub(crate) mod builder;
mod error;
pub(crate) mod markdown_it_py;
#[cfg_attr(not(test), allow(dead_code))]
mod sanitizer;
#[cfg(test)]
mod test_support;
pub(crate) mod types;
mod utils;

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
