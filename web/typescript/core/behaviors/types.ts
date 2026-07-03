export interface BehaviorContext {
  document: Document;
  signal: AbortSignal;
}

// every behavior function must return this
export interface Behavior {
  mount(root: ParentNode, context: BehaviorContext): void;
  destroy?(): void;
}
