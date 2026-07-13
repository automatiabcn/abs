/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The one button.
//
// Two things were broken here. Three of the six variants (destructive,
// secondary, and the accent hover shared by outline/ghost) named colours that
// tailwind.config.ts never defined, so Tailwind emitted no rule and twenty-five
// call sites rendered unstyled — silently, because a missing utility class is
// not an error. And every variant leaned on opacity modifiers (`bg-primary/90`),
// which cannot work now that colours resolve through `var()`: Tailwind 3 has no
// channel triple left to re-compose with an alpha. Variants now name explicit
// hover tokens, so what you read is what renders.
//
// Seventy-four hand-styled `<button>` elements across the panel are what this
// component exists to absorb. Reach for it before writing another one.
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary-hover",
        destructive:
          "bg-destructive text-destructive-foreground hover:brightness-110",
        outline:
          "border border-border bg-surface text-foreground hover:bg-surface-raised hover:border-border-strong",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-surface-sunken",
        ghost: "text-foreground hover:bg-surface-raised",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 text-sm",
        sm: "h-8 px-3 text-[13px]",
        lg: "h-11 px-7 text-[15px]",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
