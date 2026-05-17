# custom_components/solaxcloud/entity.py
"""Shared base entity for all SolaXCloud entities."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SolaxCloudCoordinator


class SolaxCloudEntity(CoordinatorEntity[SolaxCloudCoordinator]):  # type: ignore[misc]
    """Base class for all SolaXCloud entities.

    Subclasses must set ``_attr_unique_id`` and ``_attr_translation_key``
    and provide a :attr:`device_info` property via ``_attr_device_info``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: SolaxCloudCoordinator) -> None:
        """Initialise the entity with the shared coordinator."""
        super().__init__(coordinator)
