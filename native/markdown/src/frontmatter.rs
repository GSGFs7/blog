use std::sync::LazyLock;

use markdown_it::Node;
use markdown_it::parser::core::Root;
use markdown_it::plugins::extra::front_matter::{FrontMatter, FrontMatterKind};
use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use regex::Regex;

use crate::error::MarkdownError;

static YAML_DATETIME: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z| ?[+-]\d{2}:?\d{2})?$")
        .expect("valid YAML datetime regex")
});

#[derive(Debug, PartialEq)]
pub(crate) enum FrontMatterValue {
    Null,
    Bool(bool),
    Signed(i64),
    Unsigned(u64),
    Float(f64),
    String(String),
    Array(Vec<Self>),
    Object(Vec<(String, Self)>),
}

pub(crate) fn parse(root: &Node) -> Result<Option<FrontMatterValue>, MarkdownError> {
    let Some(frontmatter) = root
        .cast::<Root>()
        .and_then(|root| root.ext.get::<FrontMatter>())
    else {
        return Ok(None);
    };

    let value = match frontmatter.kind {
        FrontMatterKind::Yaml => parse_yaml(&frontmatter.raw)?,
        FrontMatterKind::Toml => parse_toml(&frontmatter.raw)?,
    };
    Ok(Some(value))
}

pub(crate) fn into_python(
    py: Python<'_>,
    value: Option<FrontMatterValue>,
) -> PyResult<Option<Py<PyDict>>> {
    value
        .map(|value| match value {
            FrontMatterValue::Object(values) => object_into_python(py, values),
            _ => unreachable!("frontmatter parser only returns top-level objects"),
        })
        .transpose()
}

// --- yaml ---

fn parse_yaml(raw: &str) -> Result<FrontMatterValue, MarkdownError> {
    let value: serde_yaml::Value =
        serde_yaml::from_str(raw).map_err(|_| MarkdownError::InvalidYamlFrontmatter)?;
    if value.is_null() {
        return Ok(FrontMatterValue::Object(Vec::new()));
    }
    let value = yaml_value(value)?;
    if !matches!(value, FrontMatterValue::Object(_)) {
        return Err(MarkdownError::FrontmatterMustBeMapping);
    }
    Ok(value)
}

fn yaml_value(value: serde_yaml::Value) -> Result<FrontMatterValue, MarkdownError> {
    use serde_yaml::Value;

    match value {
        Value::Null => Ok(FrontMatterValue::Null),
        Value::Bool(value) => Ok(FrontMatterValue::Bool(value)),
        Value::Number(value) => {
            if let Some(value) = value.as_i64() {
                Ok(FrontMatterValue::Signed(value))
            } else if let Some(value) = value.as_u64() {
                Ok(FrontMatterValue::Unsigned(value))
            } else if let Some(value) = value.as_f64() {
                finite_float(value)
            } else {
                Err(MarkdownError::UnsupportedFrontmatterValue)
            }
        }
        Value::String(value) => Ok(FrontMatterValue::String(normalize_yaml_datetime(value))),
        Value::Sequence(values) => values
            .into_iter()
            .map(yaml_value)
            .collect::<Result<Vec<_>, _>>()
            .map(FrontMatterValue::Array),
        Value::Mapping(values) => {
            let mut result = Vec::with_capacity(values.len());
            for (key, value) in values {
                let Value::String(key) = key else {
                    return Err(MarkdownError::FrontmatterKeysMustBeStrings);
                };
                result.push((key, yaml_value(value)?));
            }
            Ok(FrontMatterValue::Object(result))
        }
        Value::Tagged(_) => Err(MarkdownError::UnsupportedFrontmatterValue),
    }
}

fn normalize_yaml_datetime(value: String) -> String {
    if YAML_DATETIME.is_match(&value) {
        value
            .replacen(' ', "T", 1)
            .replace(" +", "+")
            .replace(" -", "-")
    } else {
        value
    }
}

// --- toml ---

fn parse_toml(raw: &str) -> Result<FrontMatterValue, MarkdownError> {
    let values = raw
        .parse::<toml::Table>()
        .map_err(|_| MarkdownError::InvalidTomlFrontmatter)?;
    toml_table(values)
}

fn toml_table(values: toml::Table) -> Result<FrontMatterValue, MarkdownError> {
    values
        .into_iter()
        .map(|(key, value)| Ok((key, toml_value(value)?)))
        .collect::<Result<Vec<_>, MarkdownError>>()
        .map(FrontMatterValue::Object)
}

fn toml_value(value: toml::Value) -> Result<FrontMatterValue, MarkdownError> {
    match value {
        toml::Value::String(value) => Ok(FrontMatterValue::String(value)),
        toml::Value::Integer(value) => Ok(FrontMatterValue::Signed(value)),
        toml::Value::Float(value) => finite_float(value),
        toml::Value::Boolean(value) => Ok(FrontMatterValue::Bool(value)),
        toml::Value::Datetime(value) => Ok(FrontMatterValue::String(value.to_string())),
        toml::Value::Array(values) => values
            .into_iter()
            .map(toml_value)
            .collect::<Result<Vec<_>, _>>()
            .map(FrontMatterValue::Array),
        toml::Value::Table(values) => toml_table(values),
    }
}

// --- utils ---

fn finite_float(value: f64) -> Result<FrontMatterValue, MarkdownError> {
    if value.is_finite() {
        Ok(FrontMatterValue::Float(value))
    } else {
        Err(MarkdownError::FrontmatterFloatsMustBeFinite)
    }
}

fn value_into_python(py: Python<'_>, value: FrontMatterValue) -> PyResult<Py<PyAny>> {
    match value {
        FrontMatterValue::Null => Ok(py.None()),
        FrontMatterValue::Bool(value) => value.into_py_any(py),
        FrontMatterValue::Signed(value) => value.into_py_any(py),
        FrontMatterValue::Unsigned(value) => value.into_py_any(py),
        FrontMatterValue::Float(value) => value.into_py_any(py),
        FrontMatterValue::String(value) => value.into_py_any(py),
        FrontMatterValue::Array(values) => {
            let list = PyList::empty(py);
            for value in values {
                list.append(value_into_python(py, value)?)?;
            }
            list.into_py_any(py)
        }
        FrontMatterValue::Object(values) => object_into_python(py, values)?.into_py_any(py),
    }
}

fn object_into_python(
    py: Python<'_>,
    values: Vec<(String, FrontMatterValue)>,
) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);
    for (key, value) in values {
        dict.set_item(key, value_into_python(py, value)?)?;
    }
    Ok(dict.unbind())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::builder::build;

    fn parse_source(source: &str) -> Result<Option<FrontMatterValue>, MarkdownError> {
        parse(&build().parse(source))
    }

    #[test]
    fn parses_yaml_to_json_like_values() {
        let value = parse_source(
            "---\ntitle: Test\npublished: 2025-07-23\nupdated: 2025-07-23 14:34:00+08:00\nnested:\n  values: [1, true, null]\n---",
        )
        .unwrap();

        assert_eq!(
            value,
            Some(FrontMatterValue::Object(vec![
                (
                    "title".to_owned(),
                    FrontMatterValue::String("Test".to_owned())
                ),
                (
                    "published".to_owned(),
                    FrontMatterValue::String("2025-07-23".to_owned()),
                ),
                (
                    "updated".to_owned(),
                    FrontMatterValue::String("2025-07-23T14:34:00+08:00".to_owned()),
                ),
                (
                    "nested".to_owned(),
                    FrontMatterValue::Object(vec![(
                        "values".to_owned(),
                        FrontMatterValue::Array(vec![
                            FrontMatterValue::Signed(1),
                            FrontMatterValue::Bool(true),
                            FrontMatterValue::Null,
                        ]),
                    )]),
                ),
            ])),
        );
    }

    #[test]
    fn rejects_values_outside_the_contract() {
        assert!(matches!(
            parse_source("---\n- invalid\n---"),
            Err(MarkdownError::FrontmatterMustBeMapping)
        ));
        assert!(matches!(
            parse_source("---\n1: invalid\n---"),
            Err(MarkdownError::FrontmatterKeysMustBeStrings)
        ));
        assert!(matches!(
            parse_source("+++\nvalue = nan\n+++"),
            Err(MarkdownError::FrontmatterFloatsMustBeFinite)
        ));
    }
}
