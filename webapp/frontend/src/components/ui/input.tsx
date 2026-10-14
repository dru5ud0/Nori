// Adapted from neobrutalism/neobrutalism (MIT), registry base/input.
import { Input as InputPrimitive } from '@base-ui/react/input'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return <InputPrimitive data-slot="input" className={cn('h-10 w-full min-w-0 border-2 border-black bg-input px-3 py-2 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-50', className)} {...props} />
}
