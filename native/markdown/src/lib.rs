pub(crate) mod builder;
mod code_language;
mod domain_wrapper;
mod error;
mod frontmatter;
mod image_optimizer;
mod image_wrapper;
pub(crate) mod markdown_it_py;
mod rewriter;
mod sanitizer;
mod solid_island;
mod suffix;
mod terminal;
#[cfg(test)]
mod test_support;
pub(crate) mod types;
mod utils;

use pyo3::prelude::*;

use crate::markdown_it_py::PyMarkdownIt;
use crate::types::PyRenderPlan;

#[pymodule]
fn _markdown_it_rs_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyMarkdownIt>()?;
    m.add_class::<PyRenderPlan>()?;
    Ok(())
}
