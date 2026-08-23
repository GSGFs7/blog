use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyMapping};

use crate::types::ImageMetadata;

pub(crate) fn parse_image_metadata(
    checksum: &str,
    value: &Bound<'_, PyAny>,
) -> PyResult<ImageMetadata> {
    let item = value.cast::<PyMapping>().map_err(|_| {
        PyTypeError::new_err(format!("image metadata for '{checksum}' must be a mapping"))
    })?;

    Ok(ImageMetadata {
        src: required_string(item, checksum, "src")?,
        avif_src: optional_string(item, checksum, "avif_src")?,
        webp_src: optional_string(item, checksum, "webp_src")?,
        width: optional_dimension(item, checksum, "width")?,
        height: optional_dimension(item, checksum, "height")?,
        placeholder: optional_string(item, checksum, "placeholder")?,
    })
}

fn required_string(
    item: &Bound<'_, PyMapping>,
    checksum: &str,
    field: &'static str,
) -> PyResult<String> {
    if !item.contains(field)? {
        return Err(PyValueError::new_err(format!(
            "missing image metadata '{checksum}.{field}'"
        )));
    }

    item.get_item(field)?.extract::<String>().map_err(|_| {
        PyTypeError::new_err(format!(
            "image metadata '{checksum}.{field}' must be a string"
        ))
    })
}

fn optional_string(
    item: &Bound<'_, PyMapping>,
    checksum: &str,
    field: &'static str,
) -> PyResult<Option<String>> {
    if !item.contains(field)? {
        return Ok(None);
    }

    let value = item.get_item(field)?;
    if value.is_none() {
        return Ok(None);
    }

    value.extract::<String>().map(Some).map_err(|_| {
        PyTypeError::new_err(format!(
            "image metadata '{checksum}.{field}' must be a string or None"
        ))
    })
}

fn optional_dimension(
    item: &Bound<'_, PyMapping>,
    checksum: &str,
    field: &'static str,
) -> PyResult<Option<u32>> {
    if !item.contains(field)? {
        return Ok(None);
    }

    let value = item.get_item(field)?;
    if value.is_none() {
        return Ok(None);
    }
    if value.is_instance_of::<PyBool>() {
        return Err(PyTypeError::new_err(format!(
            "image metadata '{checksum}.{field}' must be an integer or None"
        )));
    }

    let value = value.extract::<i64>().map_err(|_| {
        PyTypeError::new_err(format!(
            "image metadata '{checksum}.{field}' must be an integer or None"
        ))
    })?;

    u32::try_from(value).map(Some).map_err(|_| {
        PyValueError::new_err(format!(
            "image metadata '{checksum}.{field}' must be between 0 and {}",
            u32::MAX
        ))
    })
}
