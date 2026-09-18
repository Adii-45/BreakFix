/* Shared motion vocabulary.

   Every duration sits in the 150-400ms band the brief asks for. Anything
   hover/press related uses spring physics so it reads as physical rather than
   as a linear tween. `useReducedMotion` collapses all of it to an instant
   state change for users who ask for that. */
import { useReducedMotion } from 'motion/react';

export const EASE = [0.22, 1, 0.36, 1];

export const springTactile = { type: 'spring', stiffness: 300, damping: 25, mass: 0.6 };
export const springSoft = { type: 'spring', stiffness: 220, damping: 28 };

export const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } },
};

export const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.3, ease: EASE } },
};

/** Stagger container — ~70ms between siblings, per the brief's 60-80ms band. */
export const stagger = (delayChildren = 0, staggerChildren = 0.07) => ({
  hidden: {},
  show: { transition: { delayChildren, staggerChildren } },
});

export const viewportOnce = { once: true, amount: 0.25, margin: '0px 0px -60px 0px' };

/** Returns variants that degrade to a plain opacity swap under reduced motion. */
export function useMotionVariants() {
  const reduced = useReducedMotion();
  if (reduced) {
    return {
      fadeUp: { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.01 } } },
      fadeIn: { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.01 } } },
      stagger: () => ({ hidden: {}, show: {} }),
      spring: { duration: 0 },
      reduced: true,
    };
  }
  return { fadeUp, fadeIn, stagger, spring: springTactile, reduced: false };
}

/** Page-level cross-fade used by AnimatePresence in App. */
export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease: EASE } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.18, ease: EASE } },
};
