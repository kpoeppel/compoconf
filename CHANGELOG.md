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
- `compoconf.to_json_schema(config_class, *, title=None)`: generate a JSON Schema (draft 2020-12)
  for a config type. Dataclasses are emitted under `$defs` with `$ref` (handling shared/recursive
  configs), registered configs pin their `class_name`, and the mapping mirrors `parse_config`.
- `strict_types` option on `parse_config` / `parse_file`: when enabled, scalar fields
  (`int`/`float`/`str`) are validated rather than coerced, so mismatched/lossy values (e.g. `"5"`
  or `5.9` for an `int` field) raise instead of being silently converted. The only widening
  allowed is `int` → `float`. Defaults to off, preserving the existing lenient behavior.

### Changed

- `NonStrictDataclass._extras` is now an `init=True` field so `dataclasses.replace` round-trips
  extra attributes. The custom `__init__` still fully owns `_extras` (excluded from positional
  argument matching), so positional construction is unchanged.
- `Registry.get_class` and the empty-`LazyConfigUnion` warning now emit actionable messages: they
  list the registered options and point at importing the defining module (e.g. via
  `compoconf.load(...)`) instead of failing silently or cryptically.

### Fixed

- `dataclasses.replace` on a `NonStrictDataclass` silently dropped all extra (undeclared)
  attributes. Extras are now preserved, and an explicitly replaced extra is merged over the
  round-tripped ones.

### Documentation

- Documented non-strict dataclasses, the frozen variant, registry discovery/introspection
  (`load` / `registered`), the recommended `Type | None = None` pattern for nested typed configs,
  and the "extras are untyped plain data" contract.
