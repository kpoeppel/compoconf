# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-10-06

`0.3.0` was tagged but never published: the release workflow's version check read the wrong value
from `pyproject.toml` and failed before the upload step, so no `0.3.0` artifact exists on PyPI. The
content below is that release, under the version that actually ships.

### Upgrading from 0.2.x

Mostly additive, with three behaviour changes worth checking before you upgrade:

- **A dump now contains only what JSON and YAML can represent** — `null`, `bool`, `int`, `float`,
  `str`, array, object. `tuple` and `set`/`frozenset` fields previously came out of
  `asdict`/`dump_config` as live Python objects, which could not be written to a file at all (sets)
  or did not survive the round trip through one (tuples). They are now lists, sets sorted. This is
  what the dump contract always meant; the annotation is what restores the `tuple`/`set` on the way
  back in, so parsing is unchanged. Code that *indexes* a dumped tuple is unaffected; code that
  asserts `isinstance(dumped["field"], tuple)` or compares against a golden file is not. This now
  covers undeclared extras on a `NonStrictDataclass` as well, which previously bypassed conversion.
- **`strict` now applies to nested configs**, not just the outermost one. `strict=True` is the
  default and is unaffected; only callers who explicitly pass `strict=False` see a difference, and
  it is a loosening — configs that previously raised on a nested unknown key now parse.
- **A config field whose name shadows an inherited attribute now raises `TypeError`** instead of
  silently defaulting to that attribute. This surfaces a class of broken config class that
  previously parsed and failed later; see *Fixed* below.

### Added

- `FrozenNonStrictDataclass`: an immutable, hashable counterpart of `NonStrictDataclass`.
  Frozen instances are read-only for both declared fields and extras. Subclasses use
  `@dataclass(init=False, frozen=True)`.
- `compoconf.load(module, *, recurse=True)`: import a module (or, recursively, a package) to run
  its `@register` / `@register_interface` decorators, returning the implementation classes that
  became registered — making the previously implicit, import-driven registration explicit and
  verifiable.
- `compoconf.registered(interface=None)` and `Registry.implementations()`: introspect the registry
  (implementation names per interface, or a full `{interface: [names]}` mapping).
- `InitVar` support in `NonStrictDataclass` / `FrozenNonStrictDataclass`: InitVars participate in
  positional/keyword matching, are forwarded to `__post_init__`, and are not stored — matching
  stdlib dataclass behavior.
- `compoconf.parse_file(config_class, path, ...)`: load a JSON or YAML file (format inferred from
  the extension) and parse it into a typed config in one call.
- `enum.Enum` support in parsing and serialization: enum-typed fields parse from an existing
  member, a member name, or a member value, and serialize back to their value (round-trips and
  stays JSON/YAML-safe).
- Built-in support for common scalar stdlib types -- `pathlib.Path`, `datetime` / `date` / `time`,
  `decimal.Decimal` and `uuid.UUID` -- across parsing, serialization (`dump_config`/`asdict` emit
  JSON-safe strings) and `to_json_schema` (string schemas with `format` where applicable). They
  round-trip through their string forms.
- `compoconf.to_json_schema(config_class, *, title=None)`: generate a JSON Schema (draft 2020-12)
  for a config type. Dataclasses are emitted under `$defs` with `$ref` (handling shared/recursive
  configs), registered configs pin their `class_name`, and the mapping mirrors `parse_config`.
- `strict_types` option on `parse_config` / `parse_file`: when enabled, scalar fields
  (`int`/`float`/`str`) are validated rather than coerced, so mismatched/lossy values (e.g. `"5"`
  or `5.9` for an `int` field) raise instead of being silently converted. The only widening
  allowed is `int` → `float`. Defaults to off, preserving the existing lenient behavior.
- `compoconf.clear_parse_cache()`: drop the compiled parse plans and the resolved-annotation cache.
  Only needed by programs that generate config classes dynamically in a loop and want to release
  them; parsing stays correct either way, since the next call simply recompiles.

- `py.typed` marker: the package now declares itself typed, so downstream `mypy`/`pyright` users get
  real signatures instead of *"module is installed, but missing library stubs or py.typed marker"* on
  every import — which was an odd gap for a library whose whole premise is type-driven config
  parsing.

- Python 3.12 and 3.13 are covered by CI, and the package version is single-sourced from
  `compoconf.__version__` so the module and the distribution metadata cannot disagree.

- The release workflow's artifact actions move to the Node 24 runtime:
  `actions/upload-artifact@v4` → `@v6` and `actions/download-artifact@v4` → `@v7`, the earliest
  majors on `node24`. `actions/checkout@v6` and `actions/setup-python@v6` were already on it.

- The release workflow's "Verify version matches tag" step read the version with
  `grep "version = " pyproject.toml | head -n 1`, which also matches `minversion` and
  `target-version` elsewhere in the file. It now parses `[project].version` with `tomllib`, so it
  compares the real field and fails loudly if that field is ever absent instead of silently
  comparing something else. `[project].version` is correspondingly kept static — it cannot be
  dynamic if the workflow is to read it — and a test asserts it stays equal to
  `compoconf.__version__`.

- Removed a stray empty `__init__.py` from the repository root. Because the repository directory is
  itself named `compoconf`, that file made the root an importable (and empty) package of the same
  name, which shadowed `src/compoconf` for any tool that put the repository's parent on `sys.path`.
  It silenced `mypy` across the whole test suite — 0 reported errors became 10 real ones once it was
  gone — and broke `pylint` under `pre-commit run --all-files`. Not shipped in any artifact, so this
  affects development only.

### Performance

- `parse_config` now *compiles* each type annotation into a cached parser the first time it sees
  it, instead of re-deriving the whole decision tree for every value. Resolving type hints
  (`typing.get_type_hints`), walking union members, resolving `cfgtype` unions against the registry
  and looking up extension types used to happen once per *value* parsed; they now happen once per
  *annotation*. Measured on a 24-block nested config (`cfgtype` unions, lists, dicts, tuples,
  enums, scalars): **3.8 ms → 0.37 ms per call (~10x)**.
  - Unions of registered config classes are dispatched directly on `class_name` rather than by
    trying each member in declaration order: a 24-element list over a 12-member union whose match
    is the last member went **1.9 ms → 0.08 ms (~24x)**.
  - A dataclass now validates its key set *before* parsing field values. Since that check never
    depended on the values, this lets a union reject a member that cannot fit without first parsing
    its whole subtree — which turns nested-union parsing from exponential in nesting depth into
    linear. A depth-8 chain of nested two-member unions went **23.5 ms → 0.10 ms (~240x)**, and
    deeper configs that previously took seconds are now flat.
  - Parse error messages (which embed the offending data) are rendered only when something reads
    them, so the errors a union discards while probing its members cost nothing to produce.
  - Cached annotation resolution is invalidated by a registry-change counter, so a `cfgtype` union
    still picks up implementations registered after the first parse.

### Changed

- When data has both an unknown key and an invalid field value, `parse_config` now reports the
  unknown/missing key rather than the bad value. Previously field values were parsed first, so the
  value error surfaced and the structural problem stayed hidden until it was fixed. Both are still
  `ValueError`; only which one is reported first changed.

- `NonStrictDataclass._extras` is now an `init=True` field so `dataclasses.replace` round-trips
  extra attributes. The custom `__init__` still fully owns `_extras` (excluded from positional
  argument matching), so positional construction is unchanged.
- `Registry.get_class` and the empty-`LazyConfigUnion` warning now emit actionable messages: they
  list the registered options and point at importing the defining module (e.g. via
  `compoconf.load(...)`) instead of failing silently or cryptically.

### Fixed

- `parse_config(..., strict=False)` now reaches nested configs. `strict` was only applied to the
  outermost dataclass; every recursive call used the default `strict=True`, so relaxing it had no
  effect below the top level and the docstring gave no hint of that. It now propagates through
  fields, list/tuple/set elements, dict values and union members.

- `dump_config` now recurses into lists and tuples. Its docstring promised "a dataclass or
  dict/list of dataclasses", but only mappings were handled, so a top-level list of configs came
  back holding raw config objects and was not JSON/YAML-serializable. Tuples stay tuples, matching
  `asdict`; strings and bytes are not treated as sequences. (Sets are still passed through
  unchanged, as in `asdict`.)

- Two implementations sharing one config class no longer do so silently. `@register` writes
  `class_name` onto the config class, so the second registration took the config class over and the
  first implementation became unreachable from it — `SharedConfig().instantiate(Iface)` always built
  the later one. That case was logged at `INFO`; it now emits a `WARNING` naming both
  implementations, while a config class merely *inheriting* a name it was never registered under
  (what the `util` decorators produce) stays at `INFO`.

- `parse_config` no longer calls a field's `default_factory` just to find out whether the field has
  one. The factory's result was built and discarded for every absent factory-defaulted field on
  every parse, running user code for its side effects; `default_factory is not MISSING` answers the
  question without calling anything.

- A config field whose name shadows an attribute inherited from a base class is now rejected with a
  clear `TypeError` instead of silently defaulting to that attribute. `@dataclass` turns any class
  attribute into the default of a same-named field, so `instantiate: int` on a `ConfigInterface`
  subclass was not required and parsed to the inherited *method*. Writing an explicit default in the
  class body is still allowed — that is deliberate.

- Union parse errors now list the member that got *deepest* into the data first, instead of the one
  with the shortest message. Members were ranked by message length as a proxy for "closest match",
  which is unrelated to how well a member fit: a member failing three levels down can produce a
  short message while one rejected on its own key set produces a long one (it embeds the whole data
  blob). The `class_name` match still wins outright, and message length remains the tie-break
  between members that failed at the same depth.

- A misconfigured `classproperty` now raises `TypeError` instead of silently evaluating to `None`.
  Its `__get__` fell through to `return None` when `fget` was neither callable nor a wrapper around
  one, so the mistake surfaced as a `None` somewhere else entirely.

- The registry epoch is now bumped *after* the registry is mutated, not before. Bumping first left a
  window in which the epoch was already new while the contents were not, so a parse plan refreshed
  inside that window would cache stale `cfgtype` members stamped with the new epoch and never
  invalidate again. A mutation that raises (`pop` of a missing key) no longer bumps at all.

- `dump_config` now converts enums and the extension scalars (`Path`, `datetime`/`date`/`time`,
  `Decimal`, `UUID`) the same way `asdict` does. It only handled dataclasses, mappings and
  sequences, so `dump_config({"c": Color.RED})` returned the live enum member and
  `dump_config([Path("/a")])` the live `Path` — neither JSON- nor YAML-serializable. A value now
  dumps to the same thing whether it sits inside a config or is passed in directly.

- `set` and `frozenset` values now dump to a sorted list, so a config with a set field can be
  written to JSON/YAML. They previously came out of `asdict`/`dump_config` as live `set`/`frozenset`
  objects, which `json.dumps` and `yaml.safe_dump` both reject — the parse side already accepted an
  array and `to_json_schema` already declared one, so only the dump disagreed. Elements are sorted
  *after* conversion, since it is the written form that has to be stable: `set` iteration order is
  hash-randomized for strings, so an unsorted dump would differ from run to run and defeat diffing
  and checksums. Elements that are not mutually comparable fall back to a `repr` ordering, which is
  arbitrary but still deterministic. The annotation is what turns the array back into a set, so
  nothing is lost in the round trip.

- Tuple values now dump to a list, with their order preserved. JSON and YAML have a single array
  type and a Python tuple is not it: a JSON Schema validator rejected the dump of a `tuple` field
  even though `to_json_schema` declares an array for it, and the dump was not a fixed point — writing
  it to a file and reading it back yielded a list. As with sets, the annotation is what restores the
  tuple when parsing. (Undeclared extras on a `NonStrictDataclass` are untyped plain data by
  contract and are still passed through unconverted.)

- Undeclared extras on a `NonStrictDataclass` are now converted when dumping, like declared fields.
  `_to_dict` re-attached the raw `_extras` after conversion, so an extra holding a `set`, `Path`,
  `Enum`, `Decimal`, `UUID` or `datetime` reached the serializer as a live Python object —
  `json.dumps` rejected every one of them and `yaml.safe_dump` most — while every declared field
  serialized fine. Extras still come back from a parse as plain data rather than their original type,
  since there is no annotation to reconstruct them by; that limitation is now documented in the
  `NonStrictDataclass` docstring (and so in the API docs) and in the README.

- `Interface.cfgtype` annotations no longer break on Python 3.10. `LazyConfigUnion` and `_LazyOr`
  are used as type annotations, and Python 3.10's `typing._type_check` ends with
  `if not callable(arg): raise TypeError`, so resolving such an annotation failed with
  "Forward references must evaluate to types. Got LazyConfigUnion[...]". Any module annotating a
  field as `SomeInterface.cfgtype` — with or without `| None` — was therefore unusable on 3.10,
  even though the package advertises `requires-python = ">=3.10"`. Python 3.11 relaxed that check
  to reject only a raw tuple, which is why this was invisible there. Both proxies are now callable
  (raising a clear error if actually called, since a union of config classes has no single
  constructor), which is all 3.10 asks of a type-like object.

- Pickling and copying a config no longer goes through `__init__`. `ConfigInterface.__reduce__`
  reduced to `(cls, (), asdict(self))`, so restoring a config called `cls()` with no arguments —
  which raises `TypeError` for any config with required fields — and its `asdict` state flattened
  nested configs into plain dicts, so a nested config came back as a `dict`. Both applied to
  `copy.copy` and `copy.deepcopy` as well, which use the same protocol. Configs now use the
  default dataclass reduction, which restores state onto a new instance and recurses into nested
  configs. The same fix applies to the config classes generated by `from_annotations` and
  `partial_call`; dynamically generated classes stay picklable through `make_dataclass_picklable`.
- `dataclasses.replace` on a `NonStrictDataclass` silently dropped all extra (undeclared)
  attributes. Extras are now preserved, and an explicitly replaced extra is merged over the
  round-tripped ones.
- A `str` or `list` field value that merely *contained* `"class_name"` (as a substring or an
  element) was mistaken for a discriminated config and crashed with an unhelpful
  `TypeError: string indices must be integers`. The `class_name` discriminator is now only read
  from mapping values.

### Documentation

- Documented non-strict dataclasses, the frozen variant, registry discovery/introspection
  (`load` / `registered`), the recommended `Type | None = None` pattern for nested typed configs,
  and the "extras are untyped plain data" contract.

[Unreleased]: https://github.com/kpoeppel/compoconf/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/kpoeppel/compoconf/releases/tag/v0.3.1
