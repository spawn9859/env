#!/usr/bin/env fish
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Nathan Chancellor

function cbl_rb_hc -d "Rebase Honeycomb kernel on latest linux-next"
    in_container_msg -c; or return

    set hc_src $CBL_BLD/honeycomb
    pushd $hc_src; or return

    # Update and patch kernel
    git ru --prune origin; or return
    git rh origin/master

    for patch in $patches
        b4 shazam -l -P _ -s $patch; or return
    end

    # [PATCH] drm/amd/display: fix non-x86/PPC64 compilation
    b4 shazam -l 20220706214203.555342-1-alexander.deucher@amd.com; or return

    # Download and modify configuration
    git cl -q
    crl -o .config https://src.fedoraproject.org/rpms/kernel/raw/rawhide/f/kernel-aarch64-fedora.config
    scripts/config \
        -d DEBUG_INFO \
        -d DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
        -d LTO_NONE \
        -e CFI_CLANG \
        -e LOCALVERSION_AUTO \
        -e LTO_CLANG_THIN \
        -e SHADOW_CALL_STACK \
        -e WERROR \
        --set-val FRAME_WARN 1400 \
        --set-val NR_CPUS 16

    # Build kernel
    cbl_bld_krnl_rpm --no-config arm64; or return

    popd
end
