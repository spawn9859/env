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
    crl https://lore.kernel.org/llvm/CADnq5_OO0m2jP_2EpOfmULM+s-WeWt3ND_Xt+yAOku669rf6pA@mail.gmail.com/2-0001-drm-amd-display-fix-non-x86-PPC64-compilation.patch | git am; or return

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
