import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shown before the label. */
  icon?: ReactNode;
  /** Fill the width of the container. */
  block?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  block = false,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = ["fc-button", `fc-button--${variant}`, `fc-button--${size}`];
  if (block) classes.push("fc-button--block");
  if (className) classes.push(className);
  return (
    <button type={type} className={classes.join(" ")} {...rest}>
      {icon}
      {children}
    </button>
  );
}
