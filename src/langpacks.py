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
            logger.debug(f"Installation of the crontab failed: {e.stdout}")
            raise

    def install(self):
        """Install the langpack builder environment."""
        # Install the deb packages needed for the service
        try:
            apt.update()
            logger.debug("Apt index refreshed.")
        except CalledProcessError as e:
            logger.error(f"failed to update package cache: {e}")
            raise

        for p in PACKAGES:
            try:
                apt.add_package(p)
                logger.debug(f"Package {p} installed")
            except PackageNotFoundError:
                logger.error(f"failed to find package {p} in package cache")
                raise
            except PackageError as e:
                logger.error(f"failed to install {p}: {e}")
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
            logger.debug(f"Git clone of the code failed: {e.stdout}")
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
            logger.debug(f"Git pull of the langpack-o-matic repository failed: {e.stdout}")
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
            logger.debug(f"Build of bin/msgequal failed: {e.stdout}")
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
                    logger.debug(f"Removed the existing cache directory: {builddir}")
                except OSError as e:
                    logger.error(f"Failed to remove cache directory {builddir}: {e}")

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
            logger.debug(f"Release {release} isn't an active Ubuntu series")
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
                logger.debug(f"Directory {HOME / release} created.")
            except CalledProcessError as e:
                logger.debug(f"Creating directory failed: {e.stdout}")
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
            logger.debug(f"Downloading {download_url} failed")
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
            logger.debug(f"Building the langpacks source failed: {e.stdout}")
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
            logger.debug(f"Uploading the langpacks failed: {e.stdout}")
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
            logger.debug(f"Disabling of crontab failed: {e.stdout}")
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
            logger.debug(f"GPG key imported: {response.stdout}")
        except CalledProcessError as e:
            logger.debug(f"Importing key failed: {e.stdout}")
            raise
