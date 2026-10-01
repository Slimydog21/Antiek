import { Component, createRef, type ReactNode } from "react";

interface Props {
  blocked: boolean;
  children: ReactNode;
  className?: string;
}

/** Keep local interaction state without exposing an unavailable workspace. */
export default class RetainedContent extends Component<Props> {
  private readonly container = createRef<HTMLDivElement>();
  private suspendedFocus: HTMLElement | null = null;

  getSnapshotBeforeUpdate(previous: Props): HTMLElement | null {
    if (previous.blocked || !this.props.blocked) return null;
    const focused = document.activeElement;
    if (!(focused instanceof HTMLElement) || !this.container.current?.contains(focused)) return null;
    // Capture before hidden/inert changes native focus, including selections
    // owned by an editor that must stay mounted during the pause.
    focused.blur();
    return focused;
  }

  componentDidUpdate(previous: Props, _state: unknown, focus: HTMLElement | null): void {
    if (focus) this.suspendedFocus = focus;
    if (!previous.blocked || this.props.blocked) return;
    const target = this.suspendedFocus;
    this.suspendedFocus = null;
    if (target?.isConnected && !target.closest("[hidden], [inert]") &&
      (document.activeElement === document.body || document.activeElement === document.documentElement)) {
      target.focus({ preventScroll: true });
    }
  }

  render() {
    return <div ref={this.container} hidden={this.props.blocked} aria-hidden={this.props.blocked || undefined}
      {...(this.props.blocked ? { inert: "" } : {})} className={this.props.blocked ? "hidden" : this.props.className ?? "contents"}>
      {this.props.children}
    </div>;
  }
}
