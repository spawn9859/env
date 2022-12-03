#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Nathan Chancellor

import grp
import ipaddress
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess

import get_glibc_version as ggv


def add_user_to_group(groupname, username):
    subprocess.run(['usermod', '-aG', groupname, username], check=True)


def add_user_to_group_if_exists(groupname, username):
    if group_exists(groupname):
        add_user_to_group(groupname, username)


def apt(apt_arguments):
    subprocess.run(['apt'] + apt_arguments, check=True)


def check_ip(ip_to_check):
    ipaddress.ip_address(ip_to_check)


def check_root():
    if os.geteuid() != 0:
        raise Exception("root access is required!")


# Easier than os.walk() + shutil.chown()
def chown(new_user, folder):
    subprocess.run(['chown', '-R', f"{new_user}:{new_user}", folder], check=True)


def chpasswd(user_name, new_password):
    subprocess.run(['chpasswd'], check=True, input=f"{user_name}:{new_password}", text=True)


def chsh_fish(username):
    fish_path = shutil.which('fish')
    if not fish_path:
        raise Exception('fish not installed?')

    fish = Path(fish_path).resolve()
    if not re.search(str(fish), Path('/etc/shells').read_text(encoding='utf-8')):
        raise Exception(f"{fish} is not in /etc/shells?")

    subprocess.run(['chsh', '-s', fish, username], check=True)


def clone_env(username):
    env_tmp = Path('/tmp/env')
    if not env_tmp.exists():
        subprocess.run(['git', 'clone', 'https://github.com/nathanchance/env', env_tmp], check=True)
        chown(username, env_tmp)


def curl(curl_args):
    return subprocess.run(['curl', '-fLSs'] + curl_args, capture_output=True, check=True).stdout


def dnf(dnf_arguments):
    subprocess.run(['dnf'] + dnf_arguments, check=True)


def enable_tailscale():
    if not is_installed('tailscale'):
        return

    systemctl_enable(['tailscaled.service'])


def fetch_gpg_key(source_url, dest):
    # Use curl to avoid requests
    key_data = curl([source_url])

    # Dearmor if necessary
    if key_data[0:2] != b'\x99\x02':
        key_data = subprocess.run(['gpg', '--dearmor'],
                                  capture_output=True,
                                  check=True,
                                  input=key_data).stdout

    dest.write_bytes(key_data)


def get_active_ethernet_info():
    active_connections = subprocess.run(
        ['nmcli', '-f', 'TYPE,NAME,DEVICE', '-t', 'connection', 'show', '--active'],
        capture_output=True,
        check=True,
        text=True).stdout.strip().split('\n')
    for line in active_connections:
        line = line.strip()
        if re.search('ethernet', line):
            return line.split(':')[1:]
    return None


def get_env_root():
    env_root = Path(__file__).resolve().parent.parent.parent
    if env_root.joinpath('README.md').exists():
        return env_root
    raise Exception(f"{env_root} does not seem correct?")


def get_glibc_version():
    return ggv.get_glibc_version()


def get_hostname():
    return socket.gethostname()


def get_ip_addr_for_intf(intf):
    ip_out = subprocess.run(['ip', 'addr'], capture_output=True, check=True,
                            text=True).stdout.split('\n')
    ip_addr = None
    for line in ip_out:
        if re.search(fr'inet.*\d{{1,3}}\.\d{{1,3}}\.\d{{1,3}}\.\d{{1,3}}.*{intf}', line):
            ip_addr = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line).group(0)
            break
    check_ip(ip_addr)
    return ip_addr


def get_os_rel_val(variable):
    os_rel = Path('/usr/lib/os-release').read_text(encoding='utf-8')

    version_id_var = re.search(f"^{variable}=.*$", os_rel, flags=re.M)
    if version_id_var:
        return version_id_var.group(0).split('=')[1].replace('"', '')

    return None


def get_user():
    if 'USERNAME' in os.environ:
        return os.environ['USERNAME']

    hostname = get_hostname()
    if hostname == 'raspberrypi':
        return 'pi'

    return 'nathan'


def get_version_codename():
    return get_os_rel_val('VERSION_CODENAME')


def group_exists(group):
    try:
        grp.getgrnam(group)
    except KeyError:
        return False
    return True


def is_equinix():
    return re.search('[a|c|f|g|m|n|s|t|x]{1}[1-3]{1}-.*', get_hostname())


def is_installed(package_to_check):
    if shutil.which('pacman'):
        cmd = ['pacman', '-Q']
    elif shutil.which('dnf'):
        cmd = ['dnf', 'list', '--installed']
    elif shutil.which('dpkg'):
        cmd = ['dpkg', '-s']
    else:
        raise Exception('Not implemented for the current package manager!')

    try:
        subprocess.run(cmd + [package_to_check], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        return False
    return True


def is_virtual_machine():
    return get_hostname() in ('hyperv', 'qemu', 'vmware')


def pacman(args):
    subprocess.run(['pacman'] + args, check=True)


def podman_setup(username):
    file_text = f"{username}:100000:65536\n"

    for letter in ['g', 'u']:
        Path(f"/etc/sub{letter}id").write_text(file_text, encoding='utf-8')

    registries_conf = Path('/etc/containers/registries.conf')
    if not registries_conf.exists():
        registries_conf.write_text(
            "[registries.search]\nregistries = ['docker.io', 'ghcr.io', 'quay.io']\n",
            encoding='utf-8')


def remove_if_installed(package_to_remove):
    if is_installed(package_to_remove):
        if shutil.which('pacman'):
            pacman(['-R', '--noconfirm', package_to_remove])
        elif shutil.which('dnf'):
            dnf(['remove', '-y', package_to_remove])
        elif shutil.which('apt'):
            apt(['remove', '-y', package_to_remove])
        else:
            raise Exception('Not implemented for the current package manager!')


def set_ip_addr_for_intf(con_name, intf, ip_addr):
    nmcli_mod = ['nmcli', 'connection', 'modify', con_name]

    if '192.168.4' in ip_addr:
        gateway = '192.168.4.1'
        local_dns = '192.168.0.1'
    else:
        raise Exception(f"{ip_addr} not supported by script!")
    dns = ['8.8.8.8', '8.8.4.4', '1.1.1.1', local_dns]

    subprocess.run(nmcli_mod + ['ipv4.addresses', f"{ip_addr}/24"], check=True)
    subprocess.run(nmcli_mod + ['ipv4.dns', ' '.join(dns)], check=True)
    subprocess.run(nmcli_mod + ['ipv4.gateway', gateway], check=True)
    subprocess.run(nmcli_mod + ['ipv4.method', 'manual'], check=True)
    subprocess.run(['nmcli', 'connection', 'reload'], check=True)
    subprocess.run(['nmcli', 'connection', 'down', con_name], check=True)
    subprocess.run(['nmcli', 'connection', 'up', con_name, 'ifname', intf], check=True)

    current_ip = get_ip_addr_for_intf(intf)
    if current_ip != ip_addr:
        raise Exception(
            f"IP address of '{intf}' ('{current_ip}') did not change to requested IP address ('{ip_addr}')"
        )


def set_date_time():
    subprocess.run(['timedatectl', 'set-timezone', 'America/Phoenix'], check=True)


def setup_initial_fish_config(username):
    fish_ver = subprocess.run(['fish', '-c', 'echo $version'],
                              capture_output=True,
                              check=True,
                              text=True).stdout.strip()
    fish_ver_tup = tuple(int(x) for x in fish_ver.split('.'))
    if fish_ver_tup < (3, 4, 0):
        raise Exception(f"{fish_ver} is less than 3.4.0!")

    user_cfg = Path(f"/home/{username}/.config")
    fish_cfg = user_cfg.joinpath('fish', 'config.fish')
    if not fish_cfg.is_symlink():
        fish_cfg.parent.mkdir(mode=0o755, exist_ok=True, parents=True)
        fish_cfg_txt = (
            '# Start an ssh-agent\n'
            'if not set -q SSH_AUTH_SOCK\n'
            '    eval (ssh-agent -c)\n'
            'end\n'
            '\n'
            '# If we are in a login shell...\n'
            'status is-login\n'
            '# or Konsole, which does not use login shells by default...\n'
            'or set -q KONSOLE_VERSION\n'
            '# and we are not already in a tmux environment...\n'
            'and not set -q TMUX\n'
            '# and we have it installed,\n'
            'and command -q tmux\n'
            '# attempt to attach to a session named "main" while detaching everyone\n'
            '# else or create a new session if one does not already exist\n'
            'and tmux new-session -AD -s main\n'
            '\n'
            '# Set up user environment wrapper\n'
            'function env_setup\n'
            '    if not set -q TMUX\n'
            r"        printf '\n%bERROR: %s%b\n\n' '\033[01;31m' 'env_setup needs to be run in tmux.' '\033[0m'"
            '\n'
            '        return 1\n'
            '    end\n'
            '    if not test -d /tmp/env\n'
            '        git -C /tmp clone -q https://github.com/nathanchance/env\n'
            '    end\n'
            '    git -C /tmp/env pull -qr\n'
            '    curl -LSs https://git.io/fisher | source\n'
            '    and fisher install jorgebucaran/fisher 1>/dev/null\n'
            '    and fisher install /tmp/env/fish 1>/dev/null\n'
            '    and user_setup\n'
            'end\n')
        fish_cfg.write_text(fish_cfg_txt, encoding='utf-8')
        chown(username, user_cfg)


def setup_libvirt(username):
    # Add user to libvirt group for rootless access to system sessions.
    add_user_to_group('libvirt', username)

    # Enable libvirtd systemd service to ensure it is brought up on restart.
    systemctl_enable(['libvirtd.service'])

    # Make the default network come up automatically on restart.
    subprocess.run(['virsh', 'net-autostart', 'default'], check=True)

    # Start network if it is not already started
    net_info = subprocess.run(['virsh', 'net-info', 'default'],
                              capture_output=True,
                              check=True,
                              text=True).stdout
    if re.search('^Active.*no', net_info, flags=re.M):
        subprocess.run(['virsh', 'net-start', 'default'], check=True)


def setup_mnt_nas():
    systemd_configs = get_env_root().joinpath('configs', 'systemd')

    for file in ['mnt-nas.mount', 'mnt-nas.automount']:
        src = systemd_configs.joinpath(file)
        dst = Path('/etc/systemd/system', file)

        shutil.copyfile(src, dst)
        dst.chmod(0o644)

    systemctl_enable([file])


def setup_static_ip(requested_ip):
    for command in ['ip', 'nmcli']:
        if not shutil.which(command):
            raise Exception(f"{command} could not be found")

    # Validate that the supplied IP address is valid
    check_ip(requested_ip)

    connection_name, interface = get_active_ethernet_info()

    set_ip_addr_for_intf(connection_name, interface, requested_ip)


def setup_sudo_symlink():
    if 'PREFIX' in os.environ:
        prefix = Path(os.environ['PREFIX'])
    else:
        prefix = Path('/usr/local')
    sudo_prefix = prefix.joinpath('stow', 'sudo')
    sudo_bin = sudo_prefix.joinpath('bin', 'sudo')

    sudo_bin.parent.mkdir(exist_ok=True, parents=True)
    try:
        sudo_bin.symlink_to(shutil.which('doas'))
    except FileExistsError:
        pass
    subprocess.run(['stow', '-d', sudo_prefix.parent, '-R', sudo_prefix.name, '-v'], check=True)


def systemctl_enable(items_to_enable, now=True):
    cmd = ['systemctl', 'enable']
    if now:
        cmd += ['--now']
    cmd += items_to_enable

    subprocess.run(cmd, check=True)


def user_exists(user):
    try:
        pwd.getpwnam(user)
    except KeyError:
        return False
    return True
