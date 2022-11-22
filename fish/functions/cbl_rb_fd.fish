#!/usr/bin/env fish
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Nathan Chancellor

function cbl_rb_fd -d "Rebase generic Fedora kernel on latest linux-next"
    in_container_msg -c; or return

    set fd_src $CBL_BLD/fedora
    pushd $fd_src; or return

    # Update and patch kernel
    git ru --prune origin; or return
    git rh origin/master

    # Patching
    for patch in $patches
        b4 shazam -l -P _ -s $patch; or return
    end
    crl https://git.kernel.org/arm64/p/32d495b0c3305546f4773b9aafcd4e90188ddb9e | git am; or return # Revert "arm64/mm: Drop redundant BUG_ON(!pgtable_alloc)"
    set -a ln_commits 2b65267f70e18b00f7dcc0ec974464e44547d46c # btf_ids.h: Increase BTF_ID_LIST array size
    for hash in $ln_commits
        git -C $CBL_BLD_P/linux-next fp -1 --stdout $hash | git am; or return
    end
    # https://lore.kernel.org/CAMuHMdX-vHH5b_Qg6-CyB4kRhHaHN=HW=FeRkJ85EM7jL41Egw@mail.gmail.com/
    git rv --no-edit dbb751ffab0b764720e360efd642ba6bf076d87f; or return

    # Build kernel
    cbl_bld_krnl_rpm --cfi --lto arm64; or return

    popd
end
