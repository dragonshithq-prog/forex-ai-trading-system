"""Unit tests for core domain entities."""

import pytest
from uuid import UUID
from datetime import datetime

from forex_trading.core.domain.entities import BaseEntity, AggregateRoot
from forex_trading.core.domain.events import DomainEvent
from forex_trading.core.domain.value_objects import Money, Symbol, UniqueId, Timestamp


class TestBaseEntity:
    """Tests for BaseEntity."""

    def test_entity_has_uuid(self):
        entity = BaseEntity()
        assert isinstance(entity.id, UUID)

    def test_entity_custom_id(self):
        custom_id = UUID("12345678-1234-5678-1234-567812345678")
        entity = BaseEntity(id=custom_id)
        assert entity.id == custom_id

    def test_entity_equality(self):
        id1 = UUID("12345678-1234-5678-1234-567812345678")
        entity1 = BaseEntity(id=id1)
        entity2 = BaseEntity(id=id1)
        assert entity1 == entity2

    def test_entity_inequality(self):
        entity1 = BaseEntity()
        entity2 = BaseEntity()
        assert entity1 != entity2

    def test_entity_timestamps(self):
        before = datetime.utcnow()
        entity = BaseEntity()
        after = datetime.utcnow()
        assert before <= entity.created_at <= after


class TestAggregateRoot:
    """Tests for AggregateRoot."""

    def test_aggregate_has_events(self):
        aggregate = AggregateRoot()
        assert aggregate.domain_events == []

    def test_aggregate_add_event(self):
        aggregate = AggregateRoot()
        event = DomainEvent(event_type="test")
        aggregate.add_event(event)
        assert len(aggregate.domain_events) == 1

    def test_aggregate_clear_events(self):
        aggregate = AggregateRoot()
        event = DomainEvent(event_type="test")
        aggregate.add_event(event)
        events = aggregate.clear_events()
        assert len(events) == 1
        assert len(aggregate.domain_events) == 0


class TestMoney:
    """Tests for Money value object."""

    def test_money_creation(self):
        money = Money(100.50, "USD")
        assert money.amount == 100.50
        assert money.currency == "USD"

    def test_money_equality(self):
        money1 = Money(100, "USD")
        money2 = Money(100, "USD")
        assert money1 == money2

    def test_money_addition(self):
        money1 = Money(100, "USD")
        money2 = Money(50, "USD")
        result = money1 + money2
        assert result.amount == 150

    def test_money_subtraction(self):
        money1 = Money(100, "USD")
        money2 = Money(30, "USD")
        result = money1 - money2
        assert result.amount == 70

    def test_money_multiplication(self):
        money = Money(100, "USD")
        result = money * 1.5
        assert result.amount == 150

    def test_money_different_currency_error(self):
        money1 = Money(100, "USD")
        money2 = Money(50, "EUR")
        with pytest.raises(ValueError):
            money1 + money2


class TestSymbol:
    """Tests for Symbol value object."""

    def test_symbol_creation(self):
        symbol = Symbol("EURUSD")
        assert symbol.value == "EURUSD"

    def test_symbol_with_slash(self):
        symbol = Symbol("EUR/USD")
        assert symbol.value == "EURUSD"

    def test_symbol_base_quote(self):
        symbol = Symbol("EURUSD")
        assert symbol.base == "EUR"
        assert symbol.quote == "USD"

    def test_symbol_is_major(self):
        assert Symbol("EURUSD").is_major is True
        assert Symbol("EURJPY").is_major is False

    def test_symbol_string_representation(self):
        symbol = Symbol("EURUSD")
        assert str(symbol) == "EUR/USD"

    def test_invalid_symbol(self):
        with pytest.raises(ValueError):
            Symbol("")


class TestUniqueId:
    """Tests for UniqueId value object."""

    def test_unique_id_generation(self):
        uid = UniqueId()
        assert isinstance(uid.value, UUID)

    def test_unique_id_custom(self):
        custom = UUID("12345678-1234-5678-1234-567812345678")
        uid = UniqueId(custom)
        assert uid.value == custom

    def test_unique_id_equality(self):
        custom = UUID("12345678-1234-5678-1234-567812345678")
        uid1 = UniqueId(custom)
        uid2 = UniqueId(custom)
        assert uid1 == uid2
