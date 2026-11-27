//! Dirty-parent tracking for temporary inline fragment cleanup.
//!
//! `Document` records parent nodes that may contain unresolved temporary
//! fragments (such as emphasis delimiter runs), empty `Text` nodes, or
//! adjacent `Text` siblings so fragment cleanup can skip untouched subtrees.

use std::any::{Any, TypeId};
use std::collections::HashMap;

use super::{Document, NodeId, NodeValue, StructuralEvent, Text};
use crate::parser::inline::helpers::emph_pair::EmphMarker;

/// Lightweight classification stored in `NodeData`'s padding bytes to avoid
/// `TypeId` and vtable downcasts when attaching ordinary nodes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub(super) enum FragmentState {
    Other = 0,
    NonEmptyText = 1,
    EmptyOrEditedText = 2,
    Fragment = 3,
}

impl FragmentState {
    /// Classify a freshly constructed payload with type checks that can constant-fold.
    #[inline]
    pub(super) fn from_value<T: NodeValue>(value: &T) -> Self {
        if TypeId::of::<T>() == TypeId::of::<Text>() {
            let text = (value as &dyn Any)
                .downcast_ref::<Text>()
                .expect("checked Text TypeId");
            if text.as_str().is_empty() {
                Self::EmptyOrEditedText
            } else {
                Self::NonEmptyText
            }
        } else if TypeId::of::<T>() == TypeId::of::<EmphMarker>() {
            Self::Fragment
        } else {
            Self::Other
        }
    }

    #[inline]
    pub(super) fn is_text_kind(self) -> bool {
        matches!(self, Self::NonEmptyText | Self::EmptyOrEditedText)
    }

    /// Advance a sibling scan tracking whether the previous sibling was text.
    /// Returns `true` if encountering `self` makes the parent dirty for cleanup.
    #[inline]
    pub(super) fn advance_sibling_scan(self, prev_is_text: &mut bool) -> bool {
        match self {
            Self::Other => {
                *prev_is_text = false;
                false
            }
            Self::NonEmptyText => {
                let adjacent = *prev_is_text;
                *prev_is_text = true;
                adjacent
            }
            Self::EmptyOrEditedText | Self::Fragment => true,
        }
    }
}

impl Document {
    /// Start tracking before parsing a document with fragment cleanup enabled.
    pub(crate) fn start_cleanup_tracking(&mut self) {
        self.dirty_cleanup_parents = Some(Vec::new());
    }

    #[inline]
    pub(super) fn is_tracking_cleanup(&self) -> bool {
        self.dirty_cleanup_parents.is_some()
    }

    /// Conservatively mark an attached `Text` node's parent dirty before returning
    /// `&mut Node`, since callers may edit it through `Node::cast_mut::<Text>()`.
    ///
    /// Detached `Text` nodes stay accurately classified: `cast_mut::<Text>()`
    /// downgrades them if edited, while metadata-only edits (`set_srcmap`,
    /// `attrs_mut`, `ext_mut`) keep `NonEmptyText`.
    #[inline]
    #[track_caller]
    pub(super) fn note_node_mut_for_cleanup(&mut self, id: NodeId) {
        let attached_text_parent = match self.arena.get_mut(id) {
            Some(node) if node.data.is_text_kind() => {
                if let Some(parent) = node.parent {
                    node.data.fragment_state = FragmentState::EmptyOrEditedText;
                    Some(parent)
                } else {
                    None
                }
            }
            Some(_) => None,
            None => panic!("invalid or stale node ID: {id:?}"),
        };
        if let Some(parent) = attached_text_parent {
            self.mark_cleanup_dirty_cold(parent);
        }
    }

    /// Update dirty-parent tracking just before appending a child with `child_state`.
    #[inline]
    pub(super) fn note_child_pushed_for_cleanup(
        &mut self,
        parent: NodeId,
        child_state: FragmentState,
    ) {
        if !self.is_tracking_cleanup() {
            return;
        }

        let mut prev_is_text = matches!(child_state, FragmentState::NonEmptyText)
            && self
                .node(parent)
                .children
                .last()
                .is_some_and(|&prev| self.node(prev).data.is_text_kind());
        if child_state.advance_sibling_scan(&mut prev_is_text) {
            self.mark_cleanup_dirty(parent);
        }
    }

    /// End tracking and visit the queued parents that still belong to the root's
    /// subtree. The visitor may rewrite children and remove descendants while
    /// preserving the ancestry of surviving nodes.
    pub(crate) fn finish_cleanup_tracking(&mut self, mut visit: impl FnMut(&mut Self, NodeId)) {
        let Some(dirty) = self.dirty_cleanup_parents.take() else {
            // A core rule can replace the document before cleanup runs.
            let parents: Vec<_> = self
                .events(self.root)
                .filter_map(|event| match event {
                    StructuralEvent::Exit(node) => Some(node.id()),
                    _ => None,
                })
                .collect();
            for parent in parents {
                visit(self, parent);
            }
            return;
        };

        let mut reachable = HashMap::new();
        let mut path = Vec::new();
        for parent in dirty {
            let Some(node) = self.arena.get_mut(parent) else {
                continue;
            };
            node.data.cleanup_queued = false;

            // Share ancestor checks between candidates in deeply nested trees.
            let mut ancestor = node.parent;
            let reaches_root = loop {
                if ancestor == Some(self.root) {
                    break true;
                }
                let Some(id) = ancestor else {
                    break parent == self.root;
                };
                if let Some(&cached) = reachable.get(&id) {
                    break cached;
                }
                path.push(id);
                ancestor = self.parent(id);
            };
            for id in path.drain(..) {
                reachable.insert(id, reaches_root);
            }
            if reaches_root {
                visit(self, parent);
            }
        }
    }

    #[inline]
    pub(super) fn mark_cleanup_dirty(&mut self, parent: NodeId) {
        if let Some(dirty) = &mut self.dirty_cleanup_parents
            && let Some(node) = self.arena.get_mut(parent)
            && !node.data.cleanup_queued
        {
            node.data.cleanup_queued = true;
            dirty.push(parent);
        }
    }

    #[cold]
    fn mark_cleanup_dirty_cold(&mut self, parent: NodeId) {
        self.mark_cleanup_dirty(parent);
    }

    #[cfg(test)]
    pub(crate) fn has_dirty_cleanup_parents(&self) -> bool {
        self.dirty_cleanup_parents
            .as_ref()
            .is_some_and(|dirty| !dirty.is_empty())
    }
}
