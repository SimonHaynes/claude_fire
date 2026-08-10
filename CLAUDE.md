# Coding standard

Express intent in the code, not alongside it.

## Comments

- No comment that restates the code, labels a section, or narrates a step.
- Comment only what the code cannot say: why this approach over the obvious one, a non-obvious constraint, a source for a hardcoded figure, a deliberate deviation from a spec.
- Module and public-function docstrings carry rationale and contract (units, what a return value means when it disagrees with the request, which assumptions bind). Keep them short; drop the ones that only paraphrase the signature.
- If a comment feels necessary to explain *what* is happening, rename or restructure instead.

## Code

- Names are the documentation: `taken` vs `requested`, `real_` vs `nominal_`, slot vs account. A reader should be able to infer units and frame from the name.
- Encode conventions once and rely on them everywhere (all money real GBP unless the name says nominal; all rates decimal fractions).
- Prefer a structure that makes the invalid state unrepresentable over a check plus a comment explaining the check.
- Small functions with meaningful names beat a long function with commented blocks.

## Never commit personal data or credentials

Client names, salaries, balances, dates of birth, health notes and API keys must
never reach a commit, a test fixture, a docstring, an example or a log line.

- Real household data lives in `workspace/<name>/`, which `.gitignore` excludes.
  Never `git add -f` it, and never move a real figure out of it to make a point.
- Keys live in `.env` (gitignored). Read them with `os.environ`; document them in
  `.env.example` by name only, never with a value. Never paste a key into a
  command, a comment or a URL that gets committed.
- Anything committed needs fabricated data. `workspace/sample_client/` is the
  fixture to extend; invent new figures rather than anonymising real ones, since
  a "sanitised" balance is still the client's balance.
- Check `git status` and the diff before committing, and treat an untracked real
  client directory as correct, not as something to fix.
- A key that has been committed is burned: rotate it, do not just amend history.

## Skills, agents and other context files

These are loaded into a context window on every use, so words cost tokens on every run.

- State the rule once, in the shortest form that is still unambiguous. No preamble, no recap, no "as mentioned above".
- Prefer a table or a list of rules over prose explaining the rules.
- Give an example only where the rule alone would be misread; one example, not three.
- Cut motivation and background unless the model would apply the rule wrongly without it.
- No restating general Claude Code behaviour or things a competent reader already assumes.
- If two files overlap, one owns the content and the other points to it.
