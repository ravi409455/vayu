# Rule semantics (normative for Python, TypeScript and Kotlin)

Rules are [JsonLogic](https://jsonlogic.com). Every platform must pass every case in this folder.

- `eval_vectors.json`: raw JsonLogic behaviour we rely on. Each case is `{name, rule, data, expected}`.
  Expected values come from the reference implementation (`json-logic-js`) and are kept only where
  `jsonlogic-rs` (Python) agrees.
- `robust_vectors.json`: allowed operators x awkward values (null, wrong types, empty lists).
  Generated: reference is `json-logic-js`; kept only where `jsonlogic-rs` (errors -> null) agrees.
- `form_vectors.json`: Vayu's own form logic on top of JsonLogic (below).

## Allowed operators
`var`, `==`, `!=`, `===`, `!==`, `<`, `<=`, `>`, `>=`, `!`, `!!`, `and`, `or`, `if`, `in`, `some`,
`all`, `none`, `filter`, `reduce`, `+` (`+` exists to count inside `reduce`).

**Banned** (validator rejects them): `missing`, `missing_some`, `-`, `*`, `/`, `%`, `min`, `max`,
`cat`, `substr`, `map`. The libraries disagree on null handling there and no form needs them. Use
`{"!": [{"var": ...}]}` for "is empty". `and`/`or` need at least one argument. Literal arrays inside
rules may only contain plain values (strings, numbers, booleans, null), never nested rules.

**Evaluation never fails.** A rule that cannot apply to the data (wrong types, nulls) evaluates to
`null`, which is falsy, on every platform. Non-finite numbers (NaN, Infinity) also become `null`. (jsonlogic-rs raises where json-logic-js returns a
value; each adapter catches and returns null.)

**Unsupported combinations** (result unspecified, but never an error): ordering comparisons
(`<`, `<=`, `>`, `>=`) on booleans; `in`, `+` and the iterating operators applied to values of
the wrong type (e.g. `some` over a string, `+` on a date). 42 such cases are known to differ in
truthiness between libraries. The form builder must only offer operators that make sense for a
field's type (numbers/dates/text for ordering; lists for `in`/iteration).

## Data a rule sees
```json
{ "booking": {"<key>": value, ...}, "ops": {...}, "inspection": {...},
  "_today": "YYYY-MM-DD", "_defects": ["inspection.<key>", ...] }
```
- Rules reference fields by qualified name: `{"var": "booking.fuel_type"}`.
- **Empty values become `null`**: `null`, whitespace-only strings, `[]` and `{}`. `0` and `false` are
  **not** empty.
- **Hidden fields of the form being evaluated become `null`.** Other forms' answers are used as given
  (after the same empty normalisation).
- `_defects`: qualified keys of **visible** choice fields where the chosen option (single) or any chosen
  option (multi) has `is_defect: true`. Sorted.

## Evaluation of one form (`spec.form` is booking | ops | inspection)
1. **Truthiness** is JsonLogic's: evaluate `{"!!": [rule]}`. A missing rule (`null`) means true.
2. **Visibility** of a page, section or field is `visible` AND parent visible AND truthy(`show_if`).
   Compute it to a fixpoint: start with everything visible, build the data (hidden → null, `_defects`
   from the current visibility), recompute every container and field, and repeat until nothing changes.
   (Design-time validation rejects cycles, so this always terminates.)
3. **Derived fields** (`type: derived`) are computed after visibility from the final data:
   `overrides["<key>"]` if present and not null, else truthy(`rule`). A hidden derived field is `null`.
4. **Required** = visible AND (`required` OR truthy(`required_if`)).
5. **Errors** (one code per field):
   - `"required"`: required and empty.
   - `"check_failed"`: a cross-field check `{rule, message, fields}` evaluated falsy. A check runs only
     when every field in `fields` is visible and non-empty; each of those fields then gets the error
     (unless it already has one).

## Case format (`form_vectors.json`)
```json
{ "name": "...",
  "spec": { "form": "inspection",
            "containers": [{"id": "p1", "kind": "page", "parent": null, "visible": true, "show_if": null}],
            "fields": [{"key": "a", "type": "short_text", "section": "s1", "visible": true,
                        "show_if": null, "required": false, "required_if": null,
                        "options": [...], "rule": {...}}],
            "checks": [{"rule": {...}, "message": "...", "fields": ["a"]}] },
  "answers": {"booking": {}, "ops": {}, "inspection": {}},
  "today": "2026-10-14",
  "overrides": {"k": true},
  "expected": { "visible": {"a": true}, "required": {"a": false},
                "errors": {"a": "required"}, "derived": {"k": true}, "defects": ["inspection.a"] } }
```
Omitted spec properties take their defaults (`visible: true`, `required: false`, others `null`/`[]`).
`expected.visible` and `expected.required` are checked only for the keys listed. `errors`, `derived` and
`defects` are compared exactly.
