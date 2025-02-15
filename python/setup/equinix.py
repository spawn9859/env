#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2023 Nathan Chancellor

from argparse import ArgumentParser
from pathlib import Path
import shutil
import subprocess
import sys
import time

import deb

sys.path.append(str(Path(__file__).resolve().parents[1]))
# pylint: disable=wrong-import-position
import lib.setup  # noqa: E402
import lib.utils  # noqa: E402
# pylint: enable=wrong-import-position


def check_install_parted():
    if shutil.which('parted'):
        return

    if shutil.which('pacman'):
        lib.setup.pacman(['-Syyu', '--noconfirm', 'parted'])
    elif shutil.which('apt'):
        deb.apt_update()
        deb.apt_install(['parted'])

    raise RuntimeError('parted is needed but it cannot be installed on the current OS!')


def create_user(user_name, user_password):
    if lib.setup.user_exists(user_name):
        raise RuntimeError(f"user ('{user_name}') already exists?")

    subprocess.run(
        ['useradd', '-m', '-G', 'sudo' if lib.setup.group_exists('sudo') else 'wheel', user_name],
        check=True)
    lib.setup.chpasswd(user_name, user_password)

    root_ssh = Path.home().joinpath('.ssh')
    user_ssh = Path('/home', user_name, '.ssh')
    shutil.copytree(root_ssh, user_ssh)
    lib.setup.chown(user_name, user_ssh)


def partition_drive(drive_path, mountpoint, username):
    if '/dev/nvme' in drive_path:
        part = 'p1'
    elif '/dev/sd' in drive_path:
        part = '1'

    volume = Path(drive_path + part)

    if mountpoint.is_mount():
        raise RuntimeError(f"mountpoint ('{mountpoint}') is already mounted?")

    if volume.is_block_device():
        raise RuntimeError(f"volume ('{volume}') already exists?")

    subprocess.run(
        ['parted', '-s', drive_path, 'mklabel', 'gpt', 'mkpart', 'primary', 'ext4', '0%', '100%'],
        check=True)
    # Let everything sync up
    time.sleep(10)

    subprocess.run(['mkfs', '-t', 'ext4', volume], check=True)

    vol_uuid = subprocess.run(['blkid', '-o', 'value', '-s', 'UUID', volume],
                              capture_output=True,
                              check=True,
                              text=True).stdout.strip()

    fstab, fstab_txt = lib.utils.path_and_text('/etc/fstab')
    fstab_line = f"UUID={vol_uuid}\t{mountpoint}\text4\tnoatime\t0\t2\n"
    fstab.write_text(fstab_txt + fstab_line, encoding='utf-8')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)

    mountpoint.mkdir(exist_ok=True, parents=True)
    subprocess.run(['mount', '-a'], check=True)
    if mountpoint != Path('/home'):
        lib.setup.chown(username, mountpoint)


def parse_arguments():
    parser = ArgumentParser(description='Perform initial setup on Equinix Metal servers')

    parser.add_argument('-d',
                        '--drive',
                        help='Drive to create folder on (default: no partitioning)')
    parser.add_argument('-f',
                        '--folder',
                        default='/home',
                        help='Mountpoint of partiton (default: /home)')
    parser.add_argument('-p',
                        '--password',
                        help='Password of user account (implies account creation)')
    parser.add_argument('-u', '--user', default=lib.setup.get_user(), help='Name of user account')

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()

    lib.setup.check_root()

    drive = args.drive
    folder = Path(args.folder)
    password = args.password
    user = args.user

    if drive:
        check_install_parted()
        partition_drive(drive, folder, user)

    if password:
        create_user(user, password)
