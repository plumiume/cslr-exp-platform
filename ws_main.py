#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 plumiume
# SPDX-License-Identifier: MIT
# License: MIT License (https://opensource.org/licenses/MIT)
# See LICENSE.txt for details.

"""
Workspace CLI tool for managing Docker Compose with Jinja2 templates.

This is the main entry point that delegates to modular components in ws-src/.
"""

from ws_src.commands import main

if __name__ == "__main__":
    main()
