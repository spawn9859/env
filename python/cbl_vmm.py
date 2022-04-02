#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Nathan Chancellor
# Description: Virtual machine manager for ClangBuiltLinux development

import argparse
from pathlib import Path
import platform
import os
import shutil
import subprocess


def parse_parameters():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="Action to perform", dest="action")

    # Common arguments for all subcommands
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("-a",
                               "--architecture",
                               type=str,
                               default=platform.machine(),
                               help="Architecture of virtual machine")
    common_parser.add_argument("-n",
                               "--name",
                               type=str,
                               required=True,
                               help="Name of virtual machine")

    # Arguments for "create"
    create_parser = subparsers.add_parser("create",
                                          help="Create virtual machine files",
                                          parents=[common_parser])
    create_parser.add_argument("-s",
                               "--size",
                               type=str,
                               default="50G",
                               help="Size of virtual machine disk image")
    create_parser.set_defaults(func=create)

    # Common arguments for "setup" and "run" subcommands
    setup_run_parser = argparse.ArgumentParser(add_help=False)
    setup_run_parser.add_argument("-c",
                                  "--cores",
                                  type=int,
                                  default="8",
                                  help="Number of cores virtual machine has")
    setup_run_parser.add_argument("-m",
                                  "--memory",
                                  type=str,
                                  default="16G",
                                  help="Amount of memory virtual machine has")

    # Arguments for "setup"
    setup_parser = subparsers.add_parser(
        "setup",
        help="Run virtual machine for first time",
        parents=[common_parser, setup_run_parser])
    setup_parser.set_defaults(func=setup)

    # Arguments for "run"
    run_parser = subparsers.add_parser(
        "run",
        help="Run virtual machine after setup",
        parents=[common_parser, setup_run_parser])
    run_parser.add_argument("-k",
                            "--kernel",
                            type=str,
                            help="Path to kernel sources to boot from")
    run_parser.set_defaults(func=run)

    return parser.parse_args()


def run_cmd(cmd):
    print("$ %s" % " ".join([str(element) for element in cmd]))
    subprocess.run(cmd, check=True)


def get_disk_img(vm_folder):
    return vm_folder.joinpath("disk.img")


def get_efi_img(args, vm_folder):
    if args.architecture == "x86_64":
        efi_img = Path("/usr/share/edk2-ovmf/x64/OVMF_CODE.fd")

    if efi_img.exists():
        return efi_img

    raise RuntimeError("{} could not be found!".format(efi_img))


def get_efi_vars(args, vm_folder):
    if args.architecture == "x86_64":
        efivars_src = Path("/usr/share/OVMF/x64/OVMF_VARS.fd")

    if efivars_src.exists():
        efivars_dst = vm_folder.joinpath(efivars_src.name)
        if not efivars_dst.exists():
            shutil.copyfile(efivars_src, efivars_dst)
        return efivars_dst

    raise RuntimeError("{} could not be found!".format(efivars_src))


def get_iso(args, vm_folder):
    if args.architecture == "x86_64":
        ver = "2022.04.01"
        url = "https://mirror.arizona.edu/archlinux/iso/{0}/archlinux-{0}-x86_64.iso".format(
            ver)

    iso_dst = vm_folder.joinpath(url.split("/")[-1])
    if not iso_dst.exists():
        run_cmd(["wget", "-c", "-O", iso_dst, url])

    return iso_dst


def get_vm_folder(args):
    if not "VM_FOLDER" in os.environ:
        raise RuntimeError("VM_FOLDER is undefined")
    return Path(os.environ["VM_FOLDER"]).joinpath(args.architecture, args.name)


def default_qemu_arguments(args, vm_folder):
    # QEMU binary
    qemu = ["qemu-system-{}".format(args.architecture)]

    # No display
    qemu += ["-display", "none"]
    qemu += ["-serial", "mon:stdio"]

    # Firmware
    firmware_common = "if=pflash,format=raw,file="
    efi_img = get_efi_img(args, vm_folder)
    efi_vars = get_efi_vars(args, vm_folder)
    qemu += ["-drive", "{}{},readonly=on".format(firmware_common, efi_img)]
    qemu += ["-drive", "{}{}".format(firmware_common, efi_vars)]

    # Hard drive
    disk_img = get_disk_img(vm_folder)
    qemu += ["-drive", "if=virtio,format=qcow2,file={}".format(disk_img)]

    # KVM acceleration (when possible)
    if platform.machine() == args.architecture:
        qemu += ["-cpu", "host"]
        qemu += ["-enable-kvm"]

    # Memory
    qemu += ["-m", args.memory]

    # Networking
    qemu += ["-nic", "user,model=virtio-net-pci,hostfwd=tcp::8022-:22"]

    # Number of processor cores
    qemu += ["-smp", str(args.cores)]

    return qemu


def create(args, vm_folder):
    # Create folder
    if vm_folder.is_dir():
        shutil.rmtree(vm_folder)
    vm_folder.mkdir(parents=True, exist_ok=True)

    # Create efivars image
    get_efi_vars(args, vm_folder)

    # Create disk image
    qemu_img = ["qemu-img", "create", "-f", "qcow2"]
    qemu_img += [get_disk_img(vm_folder)]
    qemu_img += [args.size]
    run_cmd(qemu_img)

    # Download ISO image
    get_iso(args, vm_folder)


def setup(args, vm_folder):
    iso = get_iso(args, vm_folder)
    qemu = default_qemu_arguments(args, vm_folder)
    qemu += ["-device", "virtio-scsi-pci,id=scsi0"]
    qemu += ["-device", "scsi-cd,drive=cd"]
    qemu += ["-drive", "if=none,format=raw,id=cd,file={}".format(iso)]

    run_cmd(qemu)


def run(args, vm_folder):
    qemu = default_qemu_arguments(args, vm_folder)

    if args.kernel:
        kernel_folder = Path(args.kernel)
        if args.architecture == "x86_64":
            kernel = kernel_folder.joinpath("arch/x86/boot/bzImage")
            initrd = kernel_folder.joinpath("rootfs/initramfs.img")
            console = "ttyS0"

        if not kernel.exists():
            raise RuntimeError("{} could not be found!".format(kernel))
        if not initrd.exists():
            raise RuntimeError("{} could not be found!".format(kernel))

        # yapf: disable
        qemu += ["-append", "root=/dev/vda2 rw rootfstype=ext4 console={}".format(console)]
        qemu += ["-kernel", kernel]
        qemu += ["-initrd", initrd]
        # yapf: enable

    run_cmd(qemu)


def main():
    args = parse_parameters()

    if args.architecture != "x86_64":
        raise RuntimeError("{} is not currently supported!".format(
            args.architecture))

    args.func(args, get_vm_folder(args))


if __name__ == '__main__':
    main()
