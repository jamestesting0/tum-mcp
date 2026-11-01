# Building a visual explanation

Choose the obstacle to understanding before choosing an animation. Write the
source claim, the visible objects, their correspondence to symbols, and the
change that makes the reason visible. Keep one visual thread across chapters:
stable objects, locations, labels and conventions. Return to the whole object
after a close-up. Animation must carry an argument, not accompany a monologue.

## Mechanisms

| Family | Construct from prepared material | Common failure |
| --- | --- | --- |
| Transformation and invariants | Keep an initial vector, shape or equation visible; transform its parts and label what changes and what stays invariant. Match symbolic terms to those parts. | A correct final equation appears after unrelated motion; the preserved quantity is never visible. |
| Approximation and limits | Show the same object at successive source-supported resolutions. Retain a reference and the error/residual; distinguish finite approximation from its limit. | A smooth morph implies equality before a limiting argument or hides the error. |
| Signals and superposition | Build components on common axes, then show their pointwise sum with signed contributions. Link each component to its coefficient and phase. | Attractive waves do not add to the displayed result, or changing scales fake convergence. |
| Probability and conditioning | Show the sample space, restrict to the conditioning event, then renormalize the surviving mass. Preserve event/count labels and distinguish density from probability. | The denominator changes silently or an area is called a point probability. |
| Local-to-global state | Show local rule, frontier/current state and persistent global state together. Apply one update, name its reason, then repeat until the global pattern follows. | Nodes recolor without a queue/state update; a local observation is asserted as a global proof. |
| Spatial and physical reasoning | Draw the actual object, axes and conventions; isolate components or a section and map lengths/angles/forces to the equation as it is built. | A decorative object sits beside algebra with no visible term-to-object correspondence. |
| Proof and counterexample | Retain givens and the claim. Show each implication's witness or invariant; contrast an excluded case when the prepared source supplies one. | Motion merely suggests a theorem, an implication is reversed, or a special picture is treated as a general proof. |
| Representation changes | Keep both views of the same object visible long enough to map entries, basis directions, operations or states. Then use the view that simplifies the problem. | A matrix is described instead of shown, or two correct views have no explicit mapping. |

These are choices, not a quota per video. Do not manufacture a source example to
fit a row. A long construction can combine families when each advances the same
argument. If the prepared unit lacks necessary meaning, return that defect to
prepare-study before rendering.

## Scene and sentence plan

1. Establish the question and the concrete object, with needed notation introduced
   at use. Do not pre-load every label.
2. Demonstrate the bottleneck. Keep relevant before/after states visible and say
   why the change is allowed. Use `self.cue(index)` for the measured sentence.
3. Connect the demonstrated case to the general claim and its conditions. Say
   which part is illustration and which part establishes the argument.
4. Return to the whole object and check the result or limiting case.

Use complementary views when they resolve a different difficulty. Do not remove
useful reorientation to reduce repetition. Prefer sustained, legible construction
over many disconnected screens; do not optimize for runtime or animation count.
Apply the app's visual grammar and the [visual rules](visuals.md).

## Review

Watch the full sequence against the script, then inspect targeted frame intervals.
Can a newcomer point to every named object? Does each displayed state follow the
previous one? Does the visual explain why, or only reveal the answer? Recompute
states and counterexamples independently. Record defects with chapter/beat/time
under the [concept profile](../../review-course/references/media.md).

The design adapts official 3Blue1Brown exposition patterns (linear transformations,
calculus limits, Fourier construction, probability and geometric proof), alongside
Code2Video's source anchors and TheoremExplainAgent's critic/repair lessons cited
in [teaching](teaching.md). These are production heuristics, not evidence that a
particular generated lesson improves learning.
