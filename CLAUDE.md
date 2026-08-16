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

## Every tax and legislation figure carries a source and two dates

A hardcoded rate, threshold or allowance is a claim about the law **on a date**.
Without the date it reads as a claim about today, and a stale figure is wrong in
a way nobody can see.

- Every such figure needs an entry in `src/retireplan/tax/provenance.py`: the
  primary source URL, `checked_on`, `recheck_by`, and what would move it.
  gov.uk, HMRC manuals and legislation.gov.uk are primary; an adviser page is a
  way to find the primary source, never the citation.
- **`recheck_by` is the earliest date the figure could move** — the Budget, an
  April uprating, a legislated commencement date — not today plus a year. A
  freeze is not a reason to skip a check; it binds only what it names and can be
  cut short.
- **Never move `checked_on` without opening the source.** A rolled-forward date
  turns an unknown into a false assurance.
- A module's `verified_on` equals the oldest check across its sources.
  `tests/test_provenance.py` and `tools/check_tax_freshness.py` both enforce it.
- `checked_on=None` means nobody has ever checked, which is not the same as
  unchanged. Both tools treat it as overdue.
- Adding a figure with no primary source means it is an assumption, not a
  figure: put it in `standard-assumptions` with the direction it errs.

Run `tools/check_tax_freshness.py` before anything a client reads. The procedure
for clearing what it flags is the `verify-tax-figures` skill.

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

**Every person named anywhere in the repo must be on `ALLOWED_PEOPLE` in
`tools/check_no_personal_data.py`.** Adding a name is the moment to check the
figures beside it were invented too. The `.githooks/pre-commit` hook enforces
this and refuses NI numbers, sort codes, emails, keys and anything staged out of
a real `workspace/` directory. Enable it once per clone with
`tools/setup_hooks.sh`.

This applies to prose as much as to code. A test fixture and a worked example in
a skill are data like any other file, and neither `.gitignore` nor a directory
rule can see them.

Real data must not reach a memory file, a TODO, a commit message or a scratch
script either. None of those are covered by the hook.

## Skills, agents and other context files

These are loaded into a context window on every use, so words cost tokens on every run.

- State the rule once, in the shortest form that is still unambiguous. No preamble, no recap, no "as mentioned above".
- Prefer a table or a list of rules over prose explaining the rules.
- Give an example only where the rule alone would be misread; one example, not three.
- Cut motivation and background unless the model would apply the rule wrongly without it.
- No restating general Claude Code behaviour or things a competent reader already assumes.
- If two files overlap, one owns the content and the other points to it.
