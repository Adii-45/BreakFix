import { motion } from 'motion/react';
import { useMotionVariants, viewportOnce } from '../motion.js';

/** Scroll-triggered fade + rise. `once` so it never re-fires on scroll-back. */
export function Reveal({ children, delay = 0, className, as = 'div', ...rest }) {
  const v = useMotionVariants();
  const Tag = motion[as] || motion.div;
  return (
    <Tag
      className={className}
      variants={v.fadeUp}
      initial="hidden"
      whileInView="show"
      viewport={viewportOnce}
      transition={{ delay }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/** Wrap a set of siblings to stagger their reveals. Children use <RevealItem>. */
export function RevealGroup({ children, className, delayChildren = 0, staggerChildren = 0.07, ...rest }) {
  const v = useMotionVariants();
  return (
    <motion.div
      className={className}
      variants={v.stagger(delayChildren, staggerChildren)}
      initial="hidden"
      whileInView="show"
      viewport={viewportOnce}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function RevealItem({ children, className, ...rest }) {
  const v = useMotionVariants();
  return (
    <motion.div className={className} variants={v.fadeUp} {...rest}>
      {children}
    </motion.div>
  );
}
