#!/usr/bin/env fish
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2023 Nathan Chancellor

function cbl_bld_krnl_rpm -d "Build a .rpm kernel package"
    in_container_msg -c; or return
    in_kernel_tree; or return

    # Effectively 'distclean'
    git cl -e .config -q

    # Allow cross compiling
    for arg in $argv
        switch $arg
            case --cfi --cfi-permissive --lto --no-werror
                set -a gen_config_args $arg
            case -g --gcc
                set gcc true
            case -l --localmodconfig
                set lsmod /tmp/lsmod.txt
                if not test -f $lsmod
                    print_error "$lsmod not found!"
                    return 1
                end
                set -a kmake_args LSMOD=$lsmod
                set -a kmake_targets localmodconfig
            case -m --menuconfig
                set -a kmake_targets menuconfig
            case -n --no-config
                set config false
            case aarch64 arm64
                set arch arm64
            case amd64 x86_64
                set arch x86_64
        end
    end

    # If no arch value specified, use host architecture
    if not set -q arch
        switch (uname -m)
            case aarch64
                set arch arm64
            case '*'
                set arch (uname -m)
        end
    end

    if test "$config" != false
        cbl_gen_fedoraconfig $gen_config_args $arch
    end

    if set -q gcc
        set -a kmake_args \
            (korg_gcc print $GCC_VERSIONS_KERNEL[1] $arch)
    else
        set -a kmake_args \
            LLVM=1
    end

    kmake \
        ARCH=$arch \
        $kmake_args \
        RPMOPTS="--define '_topdir $PWD/rpmbuild'" \
        olddefconfig $kmake_targets binrpm-pkg; or return

    echo Run
    printf '\n\t$ sudo fish -c "dnf install %s; and reboot"\n\n' (realpath -- (fd -e rpm -u 'kernel-[0-9]+' rpmbuild) | string replace $HOME \$HOME)
    echo "to install and use new kernel."
end
