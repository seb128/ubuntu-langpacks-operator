#!/usr/bin/env python3
# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""A simple Launchpad client implementation."""

from abc import ABC

from launchpadlib.launchpad import Launchpad


class LaunchpadClientBase(ABC):
    """Basic Launchpad client interface."""

    def active_series(self):
        """Return a list of the active ubuntu series."""
        return []


class LaunchpadClient(LaunchpadClientBase):
    """Launchpad client implementation."""

    def active_series(self):
        """Return a list of the active ubuntu series."""
        lp = Launchpad.login_anonymously("langpacks", "production")
        ubuntu = lp.distributions["ubuntu"]

        active_series = []
        for s in ubuntu.series:
            if s.active:
                active_series.append(s.name)

        return active_series


class MockLaunchpadClient(LaunchpadClientBase):
    """Mock Launchpad client implementation."""

    def active_series(self):
        """Return a list of the active ubuntu series."""
        active_series = ["noble", "plucky", "questing"]

        return active_series
