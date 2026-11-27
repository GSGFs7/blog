use std::any::TypeId;

use super::cleanup::FragmentState;
use crate::common::TypeKey;
use crate::common::extset::NodeExtSet;
use crate::document::{HtmlAttributes, NodeValue, Text};

#[derive(Debug)]
pub(super) struct NodeData {
    #[cfg(feature = "sourcemap")]
    pub(super) srcmap: Option<crate::common::sourcemap::SourcePos>,
    pub(super) ext: NodeExtSet,
    pub(super) attrs: HtmlAttributes,
    pub(super) transparent: bool,
    pub(super) fragment_state: FragmentState,
    pub(super) cleanup_queued: bool,
    node_type: TypeKey,
    node_value: Box<dyn NodeValue>,
}

impl NodeData {
    pub(super) fn new<T: NodeValue>(value: T) -> Self {
        let fragment_state = FragmentState::from_value(&value);
        Self {
            #[cfg(feature = "sourcemap")]
            srcmap: None,
            ext: NodeExtSet::new(),
            attrs: Vec::new(),
            transparent: false,
            fragment_state,
            cleanup_queued: false,
            node_type: TypeKey::of::<T>(),
            node_value: Box::new(value),
        }
    }

    pub(super) fn is_text_kind(&self) -> bool {
        self.fragment_state.is_text_kind()
    }

    pub(super) fn name(&self) -> &'static str {
        self.node_type.name()
    }

    pub(super) fn type_id(&self) -> TypeId {
        self.node_type.id()
    }

    pub(super) fn is<T: NodeValue>(&self) -> bool {
        self.type_id() == TypeId::of::<T>()
    }

    pub(super) fn cast<T: NodeValue>(&self) -> Option<&T> {
        if self.is::<T>() {
            self.node_value.downcast_ref::<T>()
        } else {
            None
        }
    }

    pub(super) fn cast_mut<T: NodeValue>(&mut self) -> Option<&mut T> {
        if self.is::<T>() {
            if TypeId::of::<T>() == TypeId::of::<Text>() {
                self.fragment_state = FragmentState::EmptyOrEditedText;
            }
            self.node_value.downcast_mut::<T>()
        } else {
            None
        }
    }

    pub(super) fn replace_value(&mut self, replacement: Self) {
        self.fragment_state = replacement.fragment_state;
        self.node_type = replacement.node_type;
        self.node_value = replacement.node_value;
    }
}
