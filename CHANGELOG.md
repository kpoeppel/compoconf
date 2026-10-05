# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
