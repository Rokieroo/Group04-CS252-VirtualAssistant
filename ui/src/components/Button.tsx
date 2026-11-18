import { Children, isValidElement, type ReactNode } from "react";
import { Button as AstryxButton } from "@astryxdesign/core/Button";

function labelOf(content: ReactNode): string {
  return Children.toArray(content)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child)
        ? labelOf(child.props.children)
        : typeof child === "string" || typeof child === "number"
          ? String(child)
          : "",
    )
    .join("");
}

/** Keeps existing callers and copy while centralising size, states and theme. */
export function Button({
  children,
  onClick,
  primary = false,
  disabled = false,
}: {
  children: ReactNode;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
}) {
  return (
    <AstryxButton
      label={labelOf(children)}
      size="lg"
      variant={primary ? "primary" : "secondary"}
      isDisabled={disabled}
      className={`study-button ${primary ? "study-primary" : ""}`}
      onClick={onClick}
    >
      {children}
    </AstryxButton>
  );
}
