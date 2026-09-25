"""Dynamic Strategy Registry and Discovery Module for TapeRadar."""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Dict, List, Type

from tpt.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

_STRATEGY_REGISTRY: Dict[str, BaseStrategy] = {}


def register_strategy(strategy_instance: BaseStrategy) -> None:
    """Manually register a strategy instance into the global registry."""
    _STRATEGY_REGISTRY[strategy_instance.strategy_id] = strategy_instance
    logger.info("Registered strategy: %s (%s)", strategy_instance.name, strategy_instance.strategy_id)


def discover_strategies() -> Dict[str, BaseStrategy]:
    """Dynamically discover all BaseStrategy subclasses in tpt.strategies package."""
    if _STRATEGY_REGISTRY:
        return _STRATEGY_REGISTRY

    import tpt.strategies as strategies_pkg

    for _, module_name, is_pkg in pkgutil.iter_modules(strategies_pkg.__path__):
        if is_pkg or module_name in ("base", "registry"):
            continue
        try:
            full_module_name = f"tpt.strategies.{module_name}"
            mod = importlib.import_module(full_module_name)
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                    instance: BaseStrategy = obj()
                    _STRATEGY_REGISTRY[instance.strategy_id] = instance
                    logger.info("Discovered strategy plugin: %s (%s)", instance.name, instance.strategy_id)
        except Exception as exc:
            logger.error("Failed to load strategy module %s: %s", module_name, exc)

    return _STRATEGY_REGISTRY


def get_all_strategies() -> List[BaseStrategy]:
    """Retrieve list of all available strategy instances."""
    registry = discover_strategies()
    return list(registry.values())


def get_strategy_by_id(strategy_id: str) -> BaseStrategy | None:
    """Retrieve strategy instance by strategy_id."""
    registry = discover_strategies()
    return registry.get(strategy_id)
