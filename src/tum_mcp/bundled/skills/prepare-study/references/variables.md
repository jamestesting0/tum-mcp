# Variable meanings

A displayed formula can carry `symbols`: the variables a reader may need to recall there,
each with its meaning. The app marks those variables, and a click (or Enter on the focused
line) shows the meaning without leaving the formula. Inline math in sentences is never
marked.

| Where | Field | Required |
| --- | --- | --- |
| Exam pattern workflow step or case | `apply.symbols` for its `math` | Yes: every applied formula has meanings, here or elsewhere in the pattern |
| Cheatsheet entry | `formula.symbols` | Yes: every variable, with its general meaning (listed when the entry opens) |
| Study derivation, worked example | `derivation.symbols` | Where it helps recall |
| Exercise Guide step or Solution derivation | `derivation.symbols` | Where it helps recall |

Study `formula` blocks keep their own list (the legend) under the formula; do not repeat it as
`symbols` on the derivation right after it. A legend gives one variable per entry; group
variables only when they share one specific meaning (\(r_x, r_y, r_z\): components of the
Bloch vector). `conditions` are optional: write them when the formula holds only under them;
a formula that only states a task's givens has none.

## Once per context

A meaning written on one formula marks that variable in every derivation and applied
formula of the same Study unit, exercise or pattern. Write it where the variable is first
needed. Give a formula its own entry only where the variable means something else there.
The app underlines a variable once per block, where it first appears; later lines of the
block still list it on Enter.

## Decorated variables

\(K_j^\dagger\), \(x^*\), \(x'\), \(A^T\), \(\bar a\) and \(\hat H\) are other variables
than \(K_j\), \(x\), \(A\), \(a\) and \(H\). Give each its own entry where it appears
(\(K_j^\dagger\): adjoint of \(K_j\)); the app never shows the plain variable's meaning for
it, and applied and cheatsheet formulas without it are rejected. A power such as \(x^2\) is
no decoration.

## When a variable needs a meaning

Ask: would a student revising at this point have to stop and recall what it stands for?

- It was defined in another section, unit or lecture, or several steps earlier.
- It is compound or easy to confuse: \(\rho_A\) and \(\rho\), \(K_j^\dagger\),
  \(|\psi_i\rangle\) and \(\langle\psi_i|\).
- Its meaning shifts across the course: \(\theta\) against \(\theta/2\), \(p\) as a
  probability against \(p\) as a momentum.
- The formula is a tool the student applies (a workflow step, a guide step): recalling what
  goes in is the point.
- In a task (an exercise, a pattern's example or drill), the task gives or asks for it, lone
  letters such as \(k\) included: say what it is and its value.

Leave it out when:

- the sentence or formula block just above defines it;
- it is an index, constant or function used in the usual way (\(i\), \(e\), \(\pi\), \(\sin\));
- marking it would only add an underline: every variable in a short, just-explained formula.

Marking every letter teaches nothing; a formula with one or two marked variables shows
which ones matter. Once a variable opens its meaning, the text beside the formula (an applied
formula's `text`, a line's `reason`, a caption) does not say it again; it adds what the
formula does not show, such as when the rule holds.

## How to write one

- Say what the variable is here, in about twelve words: "probability of preparing the
  \(i\)-th state", not "probability".
- In an exercise or past question, add its value when the question gives one: "records
  searched, 16 here".
- In the cheatsheet, give the general meaning, with no values from one question.
- Never only rename it ("rho", "p sub i").
- Write the variable exactly as the formula spells it, wrapped as inline math:
  `\(|\psi_i\rangle\)` for a formula that writes `|\psi_i\rangle`. The build rejects a
  variable that does not appear in its formula.

Examples, weak then better:

- In \(\rho=\sum_i p_i\,|\psi_i\rangle\langle\psi_i|\): "\(p_i\): probability" becomes
  "\(p_i\): probability of preparing \(|\psi_i\rangle\)".
- In \(\mathcal E(\rho)=\sum_j K_j\rho K_j^\dagger\): every symbol marked becomes only
  "\(K_j\): Kraus operators of the channel" and "\(K_j^\dagger\): adjoint of \(K_j\)", with
  \(\rho\) left unmarked when the step defines it.
- In a drill's givens \(N=16,\ M=4,\ k=1\): "\(N, M, k\): given quantities" becomes
  "\(N\): records searched", "\(M\): marked records", "\(k\): iterations applied".
- In \(\theta=2\arcsin\sqrt{M/N}\) in a past question: "\(N\): number" becomes
  "\(N\): records in the database, 16 here".
- In \(T=O(V+E)\) on the cheatsheet: "\(V\): V" becomes "\(V\): number of nodes in the
  graph".

## Check

`tum-mcp study report PROJECT` flags `unexplained_symbol` (a Greek, subscripted or
decorated variable in displayed working that its context never explains; in an exercise also a
lone letter), `generic_meaning` ("given quantity"), `renamed_meaning` and
`echoed_meaning` (a meaning the text beside its formula repeats) and `redeclared_meaning`
(the same meaning written on several formulas of one context); `study
exam-report` lists the same per pattern. Each flag is a prompt: give a meaning where a
reviser would stop, and leave obvious variables alone.
