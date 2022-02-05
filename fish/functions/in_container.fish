#!/usr/bin/env fish
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Nathan Chancellor

function in_container -d "Checks if command is being run in a container"
    if test -z "$container"; or not test -f /run/.containerenv
        return 1
    end

    return 0
end