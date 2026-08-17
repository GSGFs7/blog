export interface BehaviorContext {
  document: Document;
  signal: AbortSignal;
}

// every behavior function must return this
export interface Behavior {
  mount(root: ParentNode, context: BehaviorContext): void;
  destroy?(): void;
}

export type BehaviorFactory = () => Behavior;

export interface InlineBehavior {
  selector: string;
  inline: BehaviorFactory;
}

export interface LazyBehavior {
  selector: string;
  load: () => Promise<BehaviorFactory>;
}

export type BehaviorDefinition = InlineBehavior | LazyBehavior;
