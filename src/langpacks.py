# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Representation of the langpacks service."""

import logging
import os
import shutil
from pathlib import Path
from subprocess import PIPE, STDOUT, CalledProcessError, run

import charms.operator_libs_linux.v0.apt as apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError
from launchpadlib.launchpad import Launchpad

logger = logging.getLogger(__name__)

# Packages installed as part of the update process.
PACKAGES = [
    "build-essential",
    "libgettextpo-dev",
    "debhelper",
    "fakeroot",
    "python3-launchpadlib",
    "python3-apt",
    "dput",
    "git",
    "devscripts",
    "lintian",
]

HOME = Path("~ubuntu").expanduser()
REPO_LOCATION = HOME / "langpack-o-matic"


class Langpacks:
    """Represent a langpacks instance in the workload."""

    def __init__(self):
        logger.debug("Langpacks class init")

    def setup_crontab(self):
        """Configure the crontab for the service."""
        try:
            run(
                [
                    "su",
                    "-c",
                    "crontab src/crontab",
                    "ubuntu",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Crontab configured.")
            return
        except CalledProcessError as e:
            logger.debug(
            "Installation of the crontab failed: '%s'", e.stdout)
            raise

    def install(self):
        """Install the langpack builder environment."""
        # Install the deb packages needed for the service
        try:
            apt.update()
            logger.debug("Apt index refreshed.")
        except CalledProcessError as e:
            logger.error("failed to update package cache: %s", e)
            raise

        for p in PACKAGES:
            try:
                apt.add_package(p)
                logger.debug("Package %s installed", p)
            except PackageNotFoundError:
                logger.error("failed to find package %s in package cache", p)
                raise
            except PackageError as e:
                logger.error("failed to install %s: %s", p, e)
                raise

        # Clone the langpack-o-matic repo
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "git",
                    "clone",
                    "-b",
                    "master",
                    "https://git.launchpad.net/langpack-o-matic",
                    REPO_LOCATION,
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Langpack-o-matic vcs cloned.")
        except CalledProcessError as e:
            logger.debug("Git clone of the code failed: %s", e.stdout)
            raise

    def update_checkout(self):
        """Update the langpack-o-matic checkout."""
        # Pull Vcs updates
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "git",
                    "-C",
                    REPO_LOCATION,
                    "pull",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Langpack-o-matic checkout updated.")
        except CalledProcessError as e:
            logger.debug("Git pull of the langpack-o-matic repository failed: %s", e.stdout)
            raise

        # Call make target
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "make",
                    "-C",
                    REPO_LOCATION / "bin",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Langpack-o-matic bin/msgequal build.")
        except CalledProcessError as e:
            logger.debug("Build of bin/msgequal failed %s", e.stdout)
            raise

    def _clean_builddir(self, releasedir):
        """Clean build cache."""
        if not os.path.exists(releasedir):
            return
        for builddir in (
            releasedir / "sources-base",
            releasedir / "sources-update",
        ):
            if os.path.exists(builddir):
                try:
                    shutil.rmtree(builddir)
                    logger.debug("Removed the existing cache directory: %s", builddir)
                except OSError as e:
                    logger.error("Failed to remove cache directory %s: %s", builddir, e)

    def build_langpacks(self, base, release):
        """Build the langpacks."""
        lp = Launchpad.login_anonymously("langpacks", "production")
        ubuntu = lp.distributions["ubuntu"]

        # check that the series used is valid
        active_series = []
        for s in ubuntu.series:
            if s.active:
                active_series.append(s.name)

        release = release.lower()
        devel_series = ubuntu.getDevelopmentSeries()[0].name
        if release == "devel":
            release = devel_series

        if release not in active_series:
            logger.debug("Release %s isn't an active Ubuntu series", release)
            return

        releasedir = HOME / release
        if not os.path.exists(releasedir):
            # Create target directory
            try:
                run(
                    [
                        "sudo",
                        "-u",
                        "ubuntu",
                        "mkdir",
                        HOME / release,
                    ],
                    check=True,
                    stdout=PIPE,
                    stderr=STDOUT,
                    text=True,
                )
                logger.debug("Directory %s created.", HOME / release)
            except CalledProcessError as e:
                logger.debug("Creating directory failed: %s", e.stdout)
                raise

        if base:
            download_url = (
                f"https://translations.launchpad.net/ubuntu/{release}/+latest-full-language-pack"
            )
            tarball = REPO_LOCATION / f"ubuntu-{release}-translations.tar.gz"
            import_options = ["-v", "--treshold=10"]

            # Clean existing cache directories before starting a base build
            self._clean_builddir(releasedir)

        else:
            download_url = (
                f"https://translations.launchpad.net/ubuntu/{release}/+latest-delta-language-pack"
            )
            tarball = REPO_LOCATION / f"ubuntu-{release}-translations-update.tar.gz"
            import_options = ["-v", "--update", "--treshold=10"]

        # Download the current translations tarball from launchpad
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "wget",
                    "--no-check-certificate",
                    "-q",
                    "-O",
                    tarball,
                    download_url,
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Translations tarball downloaded.")
        except CalledProcessError:
            logger.debug("Downloading %s failed", download_url)
            raise

        # Call the import script that prepares the packages
        try:
            run(
                ["sudo", "-u", "ubuntu", REPO_LOCATION / "import"]
                + import_options
                + [
                    tarball,
                    release,
                    HOME / release,
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Translations packages prepared.")
        except CalledProcessError as e:
            logger.debug("Building the langpacks source failed: %s", e.stdout)
            raise

    def upload_langpacks(self):
        """Upload the packages."""
        try:
            run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    REPO_LOCATION / "packages",
                    "upload",
                ],
                cwd=REPO_LOCATION,
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Language packs uploaded.")
        except CalledProcessError as e:
            logger.debug("Uploading the langpacks failed: %s", e.stdout)
            raise

    def disable_crontab(self):
        """Disable the crontab."""
        try:
            run(
                [
                    "su",
                    "-c",
                    "crontab -r",
                    "ubuntu",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
        except CalledProcessError as e:
            logger.debug("Disabling of crontab failed: %s", e.stdout)
            raise

    def import_gpg_key(self, key):
        """Import the private gpg key."""
        try:
            response = run(
                [
                    "sudo",
                    "-u",
                    "ubuntu",
                    "gpg",
                    "--import",
                ],
                check=True,
                input=key,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("GPG key imported: %s", response.stdout)
        except CalledProcessError as e:
            logger.debug("Importing key failed: %s", e.stdout)
            raise
