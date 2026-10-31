# Interaction pass

Work the item in the app as a student, at phone width (390 px) and desktop width, with
`tum-mcp study serve PROJECT`. Drive a browser when the host can; otherwise work from the
data and the contact sheets and say which steps you could not try. This pass scores
Practice.

The app's own tests cover its controls; this pass is about the content as the student
meets it: what feedback, hints, Compare and the solution say, in the order they appear.
Work every question and step from the data, and walk at least one question and one
exercise step of the course in the browser, where text revealed only on interaction
(feedback, Compare, explanations) is read in context.

## Procedure

1. Practice questions: answer before Check answer. Pick a wrong option first; its
   feedback must name the mistake that leads there. The hint recalls the idea without
   naming the option. Then expand the explanation of every other option.
2. Traces: step through every frame. Each caption says why its step happens, and the
   state rows change exactly as the caption says.
3. Exercise steps: try the step before opening hints, then open the hints in order: a
   pointer to the idea, the first operation worked, then Compare. Enter a wrong value in
   a table, graph or plot response and see how Compare shows the difference. Compare and
   the solution answer everything the step asked.
4. Code steps: the skeleton runs as given; the model answer does what its explanation
   claims.
5. Flashcards: the front asks one thing and the back answers exactly that.
6. Navigation: every control is reachable by keyboard and visible at phone width, the
   page never scrolls sideways, and returning to a step keeps the student's work.

## Findings

Name the step or question key and what happened: "`trace` step 3: Compare shows the
frontier but not the explored set the prompt asked for."
