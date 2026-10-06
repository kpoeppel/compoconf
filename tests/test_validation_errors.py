"""How a config's own ``__post_init__`` validation interacts with union resolution.

``__post_init__`` is where a constraint that parsing cannot check gets expressed -- "dim must be
divisible by heads". These tests pin where such an error surfaces and, just as importantly, where it
deliberately does *not*.

A union means "any of these", and a validation constraint is part of what makes a value a valid
member of a type: if one member rejects the data and another accepts it, the data is not of the
first type, so the union resolves to the second. That is the same rule as JSON Schema ``anyOf``,
which is what :func:`compoconf.to_json_schema` emits for a union. So a rejecting member is treated
as not matching, and the union moves on -- **by design, not by accident**. Promoting the error
instead would make ``Union[A, B]`` fail on data that is a perfectly good ``B``.

The error therefore surfaces wherever there is no alternative to fall through to, which is every
case that matters in practice: a direct parse, a plain declared field, and -- the common one in
compoconf -- a ``class_name``-discriminated ``cfgtype`` field, where the discriminator picks one
member outright so no alternative is ever tried.

When nothing accepts the data, the failure report ranks the members by how close each came, and a
member that failed only in its own constructor came closest of all: reaching the constructor means
every one of its fields parsed. Those tests are at the end.
"""

from dataclasses import dataclass, field
from typing import Optional, Union

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface
from compoconf.parsing import parse_config
from compoconf.util import ConfigError

# pylint: disable=C0115,C0116,W0212,W0621,W0613


@dataclass
class Rate:
    """Rejects anything outside the unit interval."""

    value: float = 0.1

    def __post_init__(self):
        if not 0 <= self.value <= 1:
            raise ValueError(f"rate {self.value} must be in [0, 1]")


@dataclass
class Unbounded:
    """Same key set as :class:`Rate`, but accepts anything."""

    value: float = 0.0


# --------------------------------------------------------------- where the error does surface


def test_validation_error_reaches_the_caller_unchanged():
    with pytest.raises(ValueError, match=r"rate 5\.0 must be in \[0, 1\]") as exc_info:
        parse_config(Rate, {"value": 5.0})
    assert type(exc_info.value) is ValueError  # pylint: disable=C0123


def test_a_custom_exception_type_survives():
    """compoconf's own ConfigError, and anything else a user raises, comes through as-is."""

    @dataclass
    class NeedsEven:
        n: int = 0

        def __post_init__(self):
            if self.n % 2:
                raise ConfigError(f"n must be even, got {self.n}")

    with pytest.raises(ConfigError, match="n must be even"):
        parse_config(NeedsEven, {"n": 3})

    @dataclass
    class RaisesKeyError:
        k: str = "a"

        def __post_init__(self):
            raise KeyError(self.k)

    with pytest.raises(KeyError):
        parse_config(RaisesKeyError, {"k": "b"})


def test_validation_error_from_a_nested_declared_field_propagates():
    @dataclass
    class Holder:
        rate: Rate = field(default_factory=Rate)

    with pytest.raises(ValueError, match="must be in"):
        parse_config(Holder, {"rate": {"value": 2.0}})


def test_validation_error_through_a_discriminated_cfgtype_field(reset_registry):
    """The case that matters in compoconf: ``class_name`` picks one member, so nothing is tried.

    The discriminator dispatches straight to the named config, bypassing the union's try-each loop
    entirely, so a validation error has nowhere to be absorbed.
    """

    @register_interface
    class Mixer(RegistrableConfigInterface):
        pass

    @dataclass
    class AttnConfig(ConfigInterface):
        heads: int = 8
        dim: int = 64

        def __post_init__(self):
            if self.dim % self.heads:
                raise ValueError(f"dim {self.dim} must be divisible by heads {self.heads}")

    @register
    class Attn(Mixer):  # pylint: disable=W0612
        config: AttnConfig

    @dataclass
    class Block:
        mixer: Optional[Mixer.cfgtype] = None

    assert parse_config(Block, {"mixer": {"class_name": "Attn", "heads": 8, "dim": 64}}).mixer.dim == 64
    with pytest.raises(ValueError, match="divisible by heads") as exc_info:
        parse_config(Block, {"mixer": {"class_name": "Attn", "heads": 7, "dim": 64}})
    # the error itself, not a "could not parse into any of" wrapper around it
    assert "Could not parse into any of" not in str(exc_info.value)


def test_a_union_with_no_accepting_member_reports_the_validation_error_first():
    """Nothing to fall through to, so the union fails -- with the real reason ranked first."""

    @dataclass
    class Other:
        different: int = 0

    with pytest.raises(ValueError) as exc_info:
        parse_config(Union[Rate, Other], {"value": 5.0})
    tried = str(exc_info.value).split("Tried:")[1]
    assert "rate 5.0 must be in [0, 1]" in tried
    assert tried.index("Rate") < tried.index("Other")


# ------------------------------------------------- where it deliberately does not surface


def test_a_union_falls_through_to_a_member_that_accepts():
    """Deliberate: a rejecting member does not match, so a union resolves to one that does.

    ``Unbounded`` accepts the same keys, and 5.0 is a perfectly good ``Unbounded``. Raising here
    instead would mean ``Union[Rate, Unbounded]`` rejects valid data for its second member, which is
    not what a union -- or JSON Schema ``anyOf`` -- means.
    """
    assert parse_config(Union[Rate, Unbounded], {"value": 5.0}) == Unbounded(5.0)


def test_fall_through_also_applies_through_a_container():
    """Same rule one level down: the rejecting member loses, the accepting one wins."""

    @dataclass
    class WithRates:
        rates: list[Rate] = field(default_factory=list)

    @dataclass
    class WithoutRates:
        rates: list[Unbounded] = field(default_factory=list)

    parsed = parse_config(Union[WithRates, WithoutRates], {"rates": [{"value": 0.5}, {"value": 9.0}]})
    assert parsed == WithoutRates([Unbounded(0.5), Unbounded(9.0)])


def test_a_valid_value_still_picks_the_first_matching_member():
    assert parse_config(Union[Rate, Unbounded], {"value": 0.5}) == Rate(0.5)


# --------------------------------------------------------------- the other mismatch signals


def test_field_parsing_failures_mean_no_match():
    """Value-discriminated unions: a field that will not parse is a mismatch, as always."""

    @dataclass
    class AsInt:
        value: int = 0

    @dataclass
    class AsStr:
        value: str = ""

    assert parse_config(Union[AsInt, AsStr], {"value": "x"}, strict_types=True) == AsStr("x")
    assert parse_config(Union[AsInt, AsStr], {"value": 3}, strict_types=True) == AsInt(3)


def test_an_unknown_key_means_no_match():
    @dataclass
    class HasA:
        a: int = 0

    @dataclass
    class HasB:
        b: int = 0

    assert parse_config(Union[HasA, HasB], {"b": 1}) == HasB(1)


# ----------------------------------------------------- ranking the closest match in a failure


def test_a_constructor_failure_outranks_a_deeper_field_failure():
    """Reaching the constructor means every field parsed, so it is the closest match.

    Without this, such a member sorted *last*: its message is the user's own, so it carries no
    ``at key`` path and scored a depth of 0 -- as if it had got nowhere.
    """

    @dataclass
    class InnerLoose:
        n: str = ""

    @dataclass
    class ViaValidation:
        cfg: InnerLoose = field(default_factory=InnerLoose)

        def __post_init__(self):
            raise ValueError("this model/optimiser combination is not supported")

    @dataclass
    class InnerStrict:
        n: int = 0

    @dataclass
    class ViaDeepField:
        cfg: InnerStrict = field(default_factory=InnerStrict)

    with pytest.raises(ValueError) as exc_info:
        parse_config(Union[ViaValidation, ViaDeepField], {"cfg": {"n": "x"}}, strict_types=True)
    tried = str(exc_info.value).split("Tried:")[1]
    assert tried.index("ViaValidation") < tried.index("ViaDeepField")


def test_a_nested_constructor_failure_ranks_its_parent_first():
    """A child's validation failure means the parent got into that child -- further than a mismatch."""

    @dataclass
    class HoldsRate:
        rate: Rate = field(default_factory=Rate)

    @dataclass
    class NeedsMore:
        required: int
        rate: Unbounded = field(default_factory=Unbounded)

    with pytest.raises(ValueError) as exc_info:
        parse_config(Union[NeedsMore, HoldsRate], {"rate": {"value": 5.0}})
    tried = str(exc_info.value).split("Tried:")[1]
    assert tried.index("HoldsRate") < tried.index("NeedsMore")
    assert "rate 5.0 must be in [0, 1]" in tried


def test_an_exact_class_name_match_still_outranks_everything():
    """Ranking by closeness must not displace the discriminator, which is exact rather than a guess."""

    @dataclass
    class AlphaConfig(ConfigInterface):
        a: int = 1

    @dataclass
    class BetaConfig(ConfigInterface):
        b: int = 1

        def __post_init__(self):
            raise ValueError("beta is never usable")

    AlphaConfig.class_name = "Alpha"
    BetaConfig.class_name = "Beta"

    # Beta reaches its constructor; Alpha does not. The class_name says Alpha, so Alpha comes first.
    with pytest.raises(ValueError) as exc_info:
        parse_config(Union[BetaConfig, AlphaConfig], {"class_name": "Alpha", "wrong": 1})
    tried = str(exc_info.value).split("Tried:")[1]
    assert tried.index("AlphaConfig") < tried.index("BetaConfig")


def test_ranking_does_not_change_which_member_wins():
    """The mark is for reporting only; resolution is untouched."""
    assert parse_config(Union[Rate, Unbounded], {"value": 5.0}) == Unbounded(5.0)
    assert parse_config(Union[Rate, Unbounded], {"value": 0.5}) == Rate(0.5)


def test_the_mark_does_not_appear_in_the_message():
    with pytest.raises(ValueError) as exc_info:
        parse_config(Rate, {"value": 5.0})
    assert str(exc_info.value) == "rate 5.0 must be in [0, 1]"
    assert "compoconf" not in str(exc_info.value)


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
