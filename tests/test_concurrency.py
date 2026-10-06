"""Tests for the process-global state behind compiled parse plans.

Parsing caches a compiled plan per annotation, caches resolved type hints, and invalidates both
against a registry epoch counter. All three live in module globals shared by every caller, so these
cover the invariant that makes the invalidation sound (a visible epoch change implies a visible
registry change) and check that concurrent parsing, concurrent registration and cache clearing do
not hand back wrong results.
"""

import threading
from dataclasses import dataclass, field
from typing import Optional

import pytest  # pylint: disable=E0401

# sibling helper module; mypy does not know pytest puts the tests directory on sys.path
from sample_configs import register_growing_mixer  # type: ignore[import-not-found]  # pylint: disable=E0401

import compoconf.compoconf as compoconf_module
import compoconf.parsing as parsing_module
from compoconf.compoconf import ConfigInterface, _EpochDict, register, registry_epoch
from compoconf.parsing import parse_config

# pylint: disable=C0115,C0116,W0212,W0621,W0613


class _EpochProbe(list):
    """Stands in for ``_REGISTRY_EPOCH`` and records what the dict looked like at each bump."""

    def __init__(self, tracked, key):
        super().__init__([0])
        self.visible_at_bump = []
        self._tracked = tracked
        self._key = key

    def __setitem__(self, index, value):
        self.visible_at_bump.append(self._key in self._tracked)
        super().__setitem__(index, value)


@pytest.mark.parametrize(
    ("mutate", "expected_visible"),
    [
        # after the bump the write must already be visible ...
        (lambda d: d.__setitem__("k", 1), True),
        (lambda d: d.update({"k": 1}), True),
        (lambda d: d.setdefault("k", 1), True),
        # ... and the removal must already be gone
        (lambda d: d.__delitem__("gone"), False),
        (lambda d: d.pop("gone"), False),
        (lambda d: d.clear(), False),
    ],
)
def test_epoch_changes_only_after_the_registry_has_changed(monkeypatch, mutate, expected_visible):
    """A reader seeing the new epoch must also see the change that caused it.

    Bumping before mutating leaves a window where the epoch is new but the contents are not, and a
    cache refreshed inside that window would store stale data stamped with the new epoch -- never to
    be invalidated again.
    """
    key = "k" if expected_visible else "gone"
    tracked = _EpochDict({"gone": 0})
    probe = _EpochProbe(tracked, key)
    monkeypatch.setattr(compoconf_module, "_REGISTRY_EPOCH", probe)

    mutate(tracked)

    assert probe.visible_at_bump == [expected_visible]


def test_a_failed_mutation_does_not_bump_the_epoch():
    """Nothing changed, so nothing should be invalidated."""
    tracked = _EpochDict()
    before = registry_epoch()
    with pytest.raises(KeyError):
        tracked.pop("absent")
    with pytest.raises(KeyError):
        del tracked["absent"]
    with pytest.raises(KeyError):
        tracked.popitem()
    assert registry_epoch() == before


# ---------------------------------------------------------------------- concurrent parsing


@dataclass
class Leaf:
    a: int = 0
    b: str = "x"


@dataclass
class Nested:
    leaf: Leaf = field(default_factory=Leaf)
    leaves: list[Leaf] = field(default_factory=list)
    mapping: dict[str, Leaf] = field(default_factory=dict)
    tag: Optional[str] = None


def _nested_data(i):
    return {
        "leaf": {"a": i, "b": f"b{i}"},
        "leaves": [{"a": i}, {"b": f"c{i}"}],
        "mapping": {"k": {"a": i}},
        "tag": f"t{i}",
    }


def _run_threads(target, count):
    """Run ``target(index)`` on ``count`` threads released simultaneously; re-raise any failure."""
    barrier = threading.Barrier(count)
    results: list = [None] * count
    errors: list = []

    def worker(index):
        try:
            barrier.wait()
            results[index] = target(index)
        except BaseException as exc:  # noqa: BLE001  # pylint: disable=W0718
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise errors[0]
    return results


def test_concurrent_first_parse_of_the_same_annotation():
    """Many threads racing to compile the same plan must all get correct results.

    The compile is not locked -- several threads may build the same plan and the last assignment
    wins -- so what matters is that a half-built plan is never published.
    """
    parsing_module.clear_parse_cache()
    expected = [parse_config(Nested, _nested_data(i)) for i in range(16)]
    parsing_module.clear_parse_cache()

    results = _run_threads(lambda i: parse_config(Nested, _nested_data(i)), 16)
    assert results == expected


def test_concurrent_parsing_of_many_different_annotations():
    """Each thread compiles a different plan, so they contend on the shared cache dict."""
    annotations = [
        int,
        str,
        float,
        bool,
        Leaf,
        Nested,
        list[int],
        list[Leaf],
        dict[str, int],
        dict[str, Leaf],
        set[int],
        frozenset[str],
        tuple[int, str],
        tuple[int, ...],
        Optional[int],
        Optional[Leaf],
    ]
    values = [
        1,
        "s",
        1.5,
        True,
        {"a": 1},
        _nested_data(1),
        [1, 2],
        [{"a": 1}],
        {"k": 1},
        {"k": {"a": 1}},
        [1, 1, 2],
        ["a"],
        [1, "a"],
        [1, 2, 3],
        None,
        None,
    ]
    parsing_module.clear_parse_cache()
    expected = [parse_config(a, v) for a, v in zip(annotations, values)]
    parsing_module.clear_parse_cache()

    results = _run_threads(lambda i: parse_config(annotations[i], values[i]), len(annotations))
    assert results == expected


def test_clearing_the_cache_while_other_threads_parse(monkeypatch):
    """A clear mid-flight may cost a recompile, but must never produce a wrong value."""
    monkeypatch.setattr(parsing_module, "_PLAN_CACHE_LIMIT", 8)  # force clears from the limit too

    def work(index):
        out = []
        for _ in range(20):
            out.append(parse_config(Nested, _nested_data(index)))
            if index % 4 == 0:
                parsing_module.clear_parse_cache()
        return out

    results = _run_threads(work, 8)
    for index, batch in enumerate(results):
        reference = parse_config(Nested, _nested_data(index))
        assert batch == [reference] * 20


def test_registering_while_other_threads_parse(reset_registry):
    """A plan cached before a registration must pick the new member up once it is visible."""

    registered = register_growing_mixer()
    Mixer, Holder = registered.interface, registered.holder

    # warm the plan (and the cfgtype resolution) while only First exists
    assert parse_config(Holder, {"impl": {"class_name": "First"}}).impl.v == 1

    late_configs = []
    for i in range(8):
        cfg_cls = dataclass(
            type(f"Late{i}Config", (ConfigInterface,), {"__annotations__": {"w": int}, "w": i, "__module__": __name__})
        )
        late_configs.append(cfg_cls)

    def work(index):
        if index % 2:
            # registrations interleaved with parses
            register(type(f"Late{index}", (Mixer,), {"config_class": late_configs[index], "__module__": __name__}))
            return None
        return parse_config(Holder, {"impl": {"class_name": "First"}}).impl.v

    results = _run_threads(work, 8)
    assert [r for r in results if r is not None] == [1, 1, 1, 1]

    # every late registration is now reachable through the plan cached before they existed
    for index in range(1, 8, 2):
        parsed = parse_config(Holder, {"impl": {"class_name": f"Late{index}", "w": index}})
        assert type(parsed.impl).__name__ == f"Late{index}Config"
        assert parsed.impl.w == index


def test_concurrent_parse_errors_stay_attributable():
    """Error messages are rendered lazily; two threads failing at once must not cross wires."""

    def work(index):
        try:
            parse_config(Nested, {"leaf": {"a": 1, f"bogus{index:02d}": 2}})
        except ValueError as exc:
            return str(exc)
        return None

    # zero-padded so no marker is a prefix of another ("bogus1" would match "bogus10")
    results = _run_threads(work, 16)
    for index, message in enumerate(results):
        assert f"bogus{index:02d}" in message
        assert sum(f"bogus{other:02d}" in message for other in range(16)) == 1


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
