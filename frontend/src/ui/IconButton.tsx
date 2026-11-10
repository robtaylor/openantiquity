import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import "./IconButton.css";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label" | "children"> {
  /** The accessible name, also shown as a tooltip. An icon alone says nothing to a screen reader. */
  label: string;
  children: ReactNode;
  size?: "sm" | "md";
  /** Use the translucent bordered look for buttons that sit on the map. */
  floating?: boolean;
  /** For toggles: whether the button is currently on. */
  pressed?: boolean;
  ref?: Ref<HTMLButtonElement>;
}

export function IconButton({
  label,
  children,
  size = "md",
  floating = false,
  pressed,
  className,
  type = "button",
  title,
  ...rest
}: IconButtonProps) {
  const classes = ["fc-icon-button", `fc-icon-button--${size}`];
  if (floating) classes.push("fc-icon-button--floating");
  if (className) classes.push(className);
  return (
    <button
      type={type}
      className={classes.join(" ")}
      aria-label={label}
      aria-pressed={pressed}
      title={title ?? label}
      {...rest}
    >
      {children}
    </button>
  );
}
